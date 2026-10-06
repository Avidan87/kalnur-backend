"""
Portion Calculator - Volume estimation from depth maps
Integrates Depth Anything V2 depth estimation with Nigerian food density values

ENHANCED: Includes Nigerian food shape priors for improved accuracy
"""

import numpy as np
import cv2
from typing import Tuple, Optional, Dict
import logging
import json
from pathlib import Path
from nigerian_food_densities import get_density, estimate_weight_from_volume
from nigerian_food_priors import NigerianFoodPriors
from reference_detector import detect_reference_object
from nigerian_food_heights import get_food_height, estimate_portion_size_category

logger = logging.getLogger(__name__)

# Load v2 database for food-specific portion limits
def load_food_database():
    """Load Nigerian foods v2 database with portion limits"""
    # Try local file first (for Railway deployment), then parent directory (local dev)
    db_path_local = Path(__file__).parent / "nigerian_foods_v2_improved.jsonl"
    db_path_parent = Path(__file__).parent.parent / "knowledge-base" / "data" / "processed" / "nigerian_foods_v2_improved.jsonl"

    # Use local path if exists (Railway), otherwise parent (local dev)
    if db_path_local.exists():
        db_path = db_path_local
        logger.info(f"📂 Loading food database from MCP server directory (Railway mode)")
    elif db_path_parent.exists():
        db_path = db_path_parent
        logger.info(f"📂 Loading food database from parent directory (local dev mode)")
    else:
        logger.error("❌ Could not find nigerian_foods_v2_improved.jsonl in any location!")
        return {}

    food_db = {}

    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            for line in f:
                food = json.loads(line)
                food_id = food.get("id", "")
                food_name = food.get("name", "").lower()
                common_servings = food.get("common_servings", {})
                density = food.get("density_g_per_ml", 0.85)

                # Store max grams and calculate max volume
                max_g = common_servings.get("max_reasonable_g", 300)
                max_volume_ml = max_g / density if density > 0 else 400

                # Store under both ID and name for flexible lookup
                food_db[food_id] = max_volume_ml
                food_db[food_name] = max_volume_ml

                # Also store aliases
                for alias in food.get("aliases", []):
                    food_db[alias.lower()] = max_volume_ml

        logger.info(f"✅ Loaded {len(food_db)} food portion limits from v2 database")
        return food_db
    except Exception as e:
        logger.warning(f"⚠️ Could not load v2 database: {e}. Using default limits.")
        return {}

# Load database once at module level
FOOD_PORTION_LIMITS = load_food_database()


class PortionCalculator:
    """Calculate portion sizes from depth maps and food images"""
    
    # Reference object sizes in cm (for scale calibration)
    REFERENCE_SIZES = {
        "hand": 18.0,  # Average adult hand width in cm
        "plate": 26.0,  # Standard dinner plate diameter in cm
        "spoon": 15.0,  # Standard tablespoon length in cm
        "fork": 18.0,   # Standard fork length in cm
        "phone": 14.0,  # Average smartphone width in cm
    }
    
    def __init__(self):
        self.pixel_to_cm_ratio = None
        self.reference_detected = False
    
    def detect_food_region(self, image: np.ndarray, depth_map: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect the food region in the image using depth and color information
        
        Args:
            image: RGB image array
            depth_map: Depth map from Depth Anything V2
        
        Returns:
            Tuple of (food_mask, food_depth_region)
        """
        # Convert to HSV for better color segmentation
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
        
        # Normalize depth map
        depth_normalized = cv2.normalize(depth_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        
        # Apply adaptive thresholding to find foreground objects
        # Assuming food is closer to camera (higher depth values in inverse depth)
        _, depth_thresh = cv2.threshold(depth_normalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Morphological operations to clean up the mask
        kernel = np.ones((5, 5), np.uint8)
        depth_thresh = cv2.morphologyEx(depth_thresh, cv2.MORPH_CLOSE, kernel)
        depth_thresh = cv2.morphologyEx(depth_thresh, cv2.MORPH_OPEN, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(depth_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if not contours:
            logger.warning("No food region detected, estimating center region")
            # CRITICAL FIX: Instead of using full image, estimate food is in center 40% of image
            # This is much more realistic than treating entire image (including table/background) as food
            height, width = image.shape[:2]
            center_x, center_y = width // 2, height // 2
            radius = min(width, height) // 5  # 40% diameter circle in center

            food_mask = np.zeros(image.shape[:2], dtype=np.uint8)
            cv2.circle(food_mask, (center_x, center_y), radius, 255, -1)

            return food_mask, np.where(food_mask == 255, depth_map, 0)
        
        # Get the largest contour (assumed to be the food)
        largest_contour = max(contours, key=cv2.contourArea)
        
        # Create mask from largest contour
        food_mask = np.zeros(image.shape[:2], dtype=np.uint8)
        cv2.drawContours(food_mask, [largest_contour], -1, 255, -1)
        
        # Extract food depth region
        food_depth = np.where(food_mask == 255, depth_map, 0)
        
        return food_mask, food_depth
    
    def calibrate_scale(self, image: np.ndarray, reference_object: Optional[str] = None) -> bool:
        """
        Calibrate pixel-to-cm ratio using REAL reference object detection

        Args:
            image: RGB image array
            reference_object: Type of reference object hint (e.g., "plate")

        Returns:
            True if calibration successful
        """
        # Use real reference detection (plate/bowl detection via Hough Circles)
        reference_size_cm = None
        if reference_object and reference_object.lower() in self.REFERENCE_SIZES:
            reference_size_cm = self.REFERENCE_SIZES[reference_object.lower()]

        # Detect actual reference object in image
        calibration = detect_reference_object(
            image,
            reference_object=reference_object,
            reference_size_cm=reference_size_cm
        )

        # Extract calibration results
        self.pixel_to_cm_ratio = calibration["pixel_to_cm_ratio"]
        self.reference_detected = calibration.get("detected", False)
        self.calibration_confidence = calibration.get("confidence", 0.3)

        if self.reference_detected:
            logger.info(
                f"✅ Reference detected: {calibration.get('object_type', 'unknown')} "
                f"({calibration.get('real_size_cm', 0)}cm), "
                f"ratio={self.pixel_to_cm_ratio:.4f} cm/pixel, "
                f"confidence={self.calibration_confidence:.2f}"
            )
        else:
            logger.warning(
                f"⚠️ No reference detected, using fallback calibration: "
                f"{self.pixel_to_cm_ratio:.4f} cm/pixel (low confidence)"
            )

        return self.reference_detected
    
    def calculate_volume_from_depth(
        self,
        depth_map: np.ndarray,
        food_mask: np.ndarray,
        pixel_to_cm: float,
        food_type: Optional[str] = None
    ) -> float:
        """
        Calculate volume from depth map using numerical integration
        WITH FOOD-SPECIFIC HEIGHT ESTIMATION

        Args:
            depth_map: Depth map array
            food_mask: Binary mask of food region
            pixel_to_cm: Pixel to centimeter conversion ratio
            food_type: Type of food for height estimation

        Returns:
            Estimated volume in milliliters (ml)
        """
        # Extract food depth values
        food_depths = depth_map[food_mask == 255]

        if len(food_depths) == 0:
            logger.warning("No food region found for volume calculation")
            return 0.0

        # Normalize depth values (inverse depth from Depth Anything V2)
        # Higher values = closer to camera = higher elevation
        depth_normalized = (food_depths - food_depths.min()) / (food_depths.max() - food_depths.min() + 1e-8)

        # Calculate pixel area in cm²
        pixel_area_cm2 = (pixel_to_cm ** 2)

        # Use FOOD-SPECIFIC height instead of hardcoded 5cm!
        if food_type:
            max_height_cm, shape_type = get_food_height(food_type, portion_size="typical")
            logger.info(f"Using food-specific height for '{food_type}': {max_height_cm}cm ({shape_type})")
        else:
            # Fallback to conservative default
            max_height_cm = 5.0
            logger.warning("No food type provided, using default height: 5cm")

        heights_cm = depth_normalized * max_height_cm

        # Calculate volume: sum of (pixel_area × height) for all pixels
        volume_cm3 = np.sum(heights_cm) * pixel_area_cm2

        # Convert cm³ to ml (1 cm³ = 1 ml)
        volume_ml = volume_cm3

        # SANITY CHECK: Cap volume at reasonable maximum using FOOD-SPECIFIC limits from v2 database
        # Look up food-specific max volume, fallback to conservative default
        max_reasonable_volume = 400.0  # Default conservative limit

        if food_type:
            # Try exact match, then lowercase normalized match
            food_key = food_type.lower()
            if food_key in FOOD_PORTION_LIMITS:
                max_reasonable_volume = FOOD_PORTION_LIMITS[food_key]
                logger.info(f"Using food-specific volume cap for '{food_type}': {max_reasonable_volume:.0f}ml")
            else:
                # Try partial match (e.g., "fried plantain" matches "plantain")
                for key, limit in FOOD_PORTION_LIMITS.items():
                    if key in food_key or food_key in key:
                        max_reasonable_volume = limit
                        logger.info(f"Using partial match volume cap for '{food_type}': {max_reasonable_volume:.0f}ml (matched '{key}')")
                        break

        if volume_ml > max_reasonable_volume:
            logger.warning(
                f"⚠️ Volume {volume_ml:.0f}ml exceeds food-specific maximum ({max_reasonable_volume:.0f}ml for '{food_type}'). "
                f"Capping to {max_reasonable_volume:.0f}ml. This suggests calibration or segmentation error."
            )
            volume_ml = max_reasonable_volume

        logger.info(f"Calculated volume: {volume_ml:.2f} ml from {len(food_depths)} pixels (max_height={max_height_cm}cm)")

        return volume_ml
    
    def estimate_portion(
        self,
        image: np.ndarray,
        depth_map: np.ndarray,
        food_type: Optional[str] = None,
        reference_object: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Complete portion estimation pipeline
        
        Args:
            image: RGB image array
            depth_map: Depth map from Depth Anything V2
            food_type: Type of Nigerian food for density lookup
            reference_object: Reference object for scale calibration
        
        Returns:
            Dictionary with volume, weight, and confidence estimates
        """
        # Step 1: Calibrate scale
        reference_detected = self.calibrate_scale(image, reference_object)

        # Step 2: Detect food region
        food_mask, food_depth = self.detect_food_region(image, depth_map)

        # Step 3: Calculate volume WITH food-specific height
        volume_ml = self.calculate_volume_from_depth(
            depth_map,
            food_mask,
            self.pixel_to_cm_ratio,
            food_type=food_type  # Pass food type for height estimation
        )
        
        # Step 4: Convert to weight using food density
        if food_type:
            weight_grams = estimate_weight_from_volume(volume_ml, food_type)
        else:
            # Use default density if food type not specified
            weight_grams = volume_ml * 0.90  # Default density
        
        # Step 5: Calculate confidence
        # Use calibration confidence as base, then adjust
        if reference_detected:
            confidence = self.calibration_confidence
        else:
            confidence = 0.3  # Low confidence without reference

        # Boost confidence if food region is clear
        if np.sum(food_mask) > (food_mask.size * 0.1):  # Food covers >10% of image
            confidence += 0.1
        if food_type:  # Food type specified (enables height calibration)
            confidence += 0.1

        confidence = min(confidence, 0.85)  # Cap at 85% (we're honest now!)
        
        return {
            "volume_ml": float(volume_ml),
            "weight_grams": float(weight_grams),
            "confidence": float(confidence),
            "reference_detected": reference_detected,
            "food_pixels": int(np.sum(food_mask == 255)),
            "pixel_to_cm_ratio": float(self.pixel_to_cm_ratio)
        }


def estimate_portion_from_depth(
    image: np.ndarray,
    depth_map: np.ndarray,
    food_type: Optional[str] = None,
    reference_object: Optional[str] = None
) -> Dict[str, float]:
    """
    Convenience function for portion estimation with Nigerian food priors

    Args:
        image: RGB image array
        depth_map: Depth map from Depth Anything V2 (already enhanced with refinement)
        food_type: Type of Nigerian food
        reference_object: Reference object for scale

    Returns:
        Portion estimation results
    """
    calculator = PortionCalculator()

    # Apply food-specific shape priors if food type provided
    enhanced_depth = depth_map
    if food_type:
        logger.info(f"Applying shape priors for food type: {food_type}")
        # Detect food region first
        food_mask, _ = calculator.detect_food_region(image, depth_map)

        # Apply Nigerian food shape constraints
        prior_engine = NigerianFoodPriors()
        enhanced_depth = prior_engine.apply_shape_prior(
            depth_map,
            food_mask,
            food_type
        )

    # Calculate portion with enhanced depth map
    return calculator.estimate_portion(image, enhanced_depth, food_type, reference_object)
