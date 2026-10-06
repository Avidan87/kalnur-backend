"""
Reference Object Detector for Scale Calibration
Detects plates, bowls, and other circular reference objects in food images

Based on OpenCV Hough Circle Transform best practices:
- https://docs.opencv.org/3.4/d4/d70/tutorial_hough_circle.html
- https://pyimagesearch.com/2014/07/21/detecting-circles-images-using-opencv-hough-circles/
"""

import cv2
import numpy as np
from typing import Optional, Tuple, Dict, List
import logging

logger = logging.getLogger(__name__)


class ReferenceObjectDetector:
    """Detect and measure reference objects (plates, bowls) for scale calibration"""

    # Known real-world sizes for Nigerian context (in cm)
    REFERENCE_SIZES = {
        "plate_small": 20.0,      # Small side plate
        "plate_medium": 24.0,     # Standard dinner plate
        "plate_large": 28.0,      # Large serving plate
        "bowl_small": 12.0,       # Small bowl diameter
        "bowl_medium": 16.0,      # Medium bowl diameter
        "bowl_large": 20.0,       # Large bowl diameter
        "spoon": 15.0,            # Table spoon length
        "hand": 18.0,             # Average hand width
    }

    def __init__(self):
        self.detected_circles = []
        self.best_reference = None

    def detect_circular_objects(
        self,
        image: np.ndarray,
        min_radius: int = 30,
        max_radius: int = 300
    ) -> List[Tuple[int, int, int]]:
        """
        Detect circular objects (plates, bowls) in image using Hough Circle Transform

        Args:
            image: RGB image array
            min_radius: Minimum circle radius in pixels
            max_radius: Maximum circle radius in pixels

        Returns:
            List of (x, y, radius) tuples for detected circles
        """
        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image.copy()

        # Apply Gaussian blur to reduce noise
        # Kernel size must be odd (5x5 is good balance)
        blurred = cv2.GaussianBlur(gray, (5, 5), 1.5)

        # Detect circles using Hough Circle Transform
        # Parameters tuned for plate/bowl detection:
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,              # Inverse accumulator resolution ratio
            minDist=50,          # Minimum distance between circle centers
            param1=100,          # Canny edge detection high threshold
            param2=30,           # Accumulator threshold (lower = more false positives)
            minRadius=min_radius,
            maxRadius=max_radius
        )

        detected = []
        if circles is not None:
            # Convert to integer coordinates
            circles = np.round(circles[0, :]).astype("int")

            for (x, y, r) in circles:
                detected.append((x, y, r))

            logger.info(f"Detected {len(detected)} circular objects")
        else:
            logger.warning("No circular objects detected")

        self.detected_circles = detected
        return detected

    def classify_reference_object(
        self,
        radius_pixels: int,
        image_width: int
    ) -> Tuple[str, float]:
        """
        Classify detected circle as plate/bowl and estimate real-world size

        Args:
            radius_pixels: Circle radius in pixels
            image_width: Image width in pixels

        Returns:
            Tuple of (object_type, estimated_size_cm)
        """
        # Calculate what % of image width the circle takes
        diameter_pixels = radius_pixels * 2
        width_ratio = diameter_pixels / image_width

        # Classification based on size ratio
        # Assumes typical food photography (plate fills 40-70% of frame)

        if width_ratio > 0.6:
            # Large object, likely serving plate
            return ("plate_large", self.REFERENCE_SIZES["plate_large"])
        elif width_ratio > 0.4:
            # Medium object, likely dinner plate
            return ("plate_medium", self.REFERENCE_SIZES["plate_medium"])
        elif width_ratio > 0.25:
            # Smaller object, could be small plate or large bowl
            return ("plate_small", self.REFERENCE_SIZES["plate_small"])
        elif width_ratio > 0.15:
            # Bowl-sized object
            return ("bowl_medium", self.REFERENCE_SIZES["bowl_medium"])
        else:
            # Very small, might be bowl or error
            return ("bowl_small", self.REFERENCE_SIZES["bowl_small"])

    def find_best_reference(
        self,
        image: np.ndarray
    ) -> Optional[Dict[str, any]]:
        """
        Find the best reference object for scale calibration

        Args:
            image: RGB image array

        Returns:
            Dictionary with reference object info or None if not found
        """
        height, width = image.shape[:2]

        # Detect circles (plates/bowls)
        circles = self.detect_circular_objects(
            image,
            min_radius=int(width * 0.1),   # At least 10% of image width
            max_radius=int(width * 0.45)   # At most 45% of image width
        )

        if not circles:
            return None

        # Find the largest circle (most likely to be the plate)
        # Sort by radius (descending)
        circles_sorted = sorted(circles, key=lambda c: c[2], reverse=True)

        best_circle = circles_sorted[0]
        x, y, radius = best_circle

        # Classify the reference object
        obj_type, real_size_cm = self.classify_reference_object(radius, width)

        # Calculate pixel-to-cm ratio
        diameter_pixels = radius * 2
        pixel_to_cm_ratio = real_size_cm / diameter_pixels

        # Calculate confidence based on circle quality
        # Higher confidence if circle is large and well-centered
        center_distance = np.sqrt((x - width/2)**2 + (y - height/2)**2)
        max_distance = np.sqrt((width/2)**2 + (height/2)**2)
        center_score = 1.0 - (center_distance / max_distance)

        # Size score: prefer circles that are 30-60% of image width
        size_ratio = diameter_pixels / width
        if 0.3 <= size_ratio <= 0.6:
            size_score = 1.0
        elif 0.2 <= size_ratio < 0.3 or 0.6 < size_ratio <= 0.7:
            size_score = 0.7
        else:
            size_score = 0.5

        confidence = (center_score * 0.4 + size_score * 0.6)

        reference_info = {
            "object_type": obj_type,
            "real_size_cm": real_size_cm,
            "pixel_radius": radius,
            "pixel_diameter": diameter_pixels,
            "pixel_to_cm_ratio": pixel_to_cm_ratio,
            "center_x": x,
            "center_y": y,
            "confidence": confidence,
            "detected": True
        }

        self.best_reference = reference_info

        logger.info(
            f"Reference detected: {obj_type} ({real_size_cm}cm), "
            f"ratio={pixel_to_cm_ratio:.4f} cm/pixel, confidence={confidence:.2f}"
        )

        return reference_info

    def calibrate_from_reference(
        self,
        image: np.ndarray,
        reference_object: Optional[str] = None,
        reference_size_cm: Optional[float] = None
    ) -> Dict[str, any]:
        """
        Calibrate scale using detected reference object

        Args:
            image: RGB image array
            reference_object: Optional hint about reference type ("plate", "bowl", etc.)
            reference_size_cm: Optional known size of reference object in cm

        Returns:
            Calibration result dictionary
        """
        # Attempt to detect reference automatically
        reference_info = self.find_best_reference(image)

        if reference_info is None:
            # Fallback: use default calibration if no reference found
            height, width = image.shape[:2]
            # CRITICAL FIX: Reduced from 40cm to 28cm (more realistic for phone food photos)
            # Typical phone photos of food on a plate are taken at ~25-30cm field of view
            default_ratio = 28.0 / width  # Assume 28cm image width (was 40cm - too large!)

            logger.warning("No reference object detected, using conservative fallback calibration (28cm width)")

            return {
                "pixel_to_cm_ratio": default_ratio,
                "detected": False,
                "confidence": 0.3,  # Low confidence
                "object_type": "none",
                "fallback_used": True,
                "message": "Using default calibration (no reference detected)"
            }

        # If user provided specific reference info, use it to refine
        if reference_size_cm is not None and reference_info["detected"]:
            # Override detected size with user-provided size
            diameter_pixels = reference_info["pixel_diameter"]
            pixel_to_cm_ratio = reference_size_cm / diameter_pixels
            reference_info["pixel_to_cm_ratio"] = pixel_to_cm_ratio
            reference_info["real_size_cm"] = reference_size_cm
            reference_info["confidence"] = min(reference_info["confidence"] + 0.1, 0.95)
            logger.info(f"Using user-provided reference size: {reference_size_cm}cm")

        return reference_info


# Convenience function for use in portion_calculator
def detect_reference_object(
    image: np.ndarray,
    reference_object: Optional[str] = None,
    reference_size_cm: Optional[float] = None
) -> Dict[str, any]:
    """
    Detect and calibrate scale using reference object

    Args:
        image: RGB image array
        reference_object: Optional reference type hint
        reference_size_cm: Optional known reference size

    Returns:
        Calibration result with pixel_to_cm_ratio
    """
    detector = ReferenceObjectDetector()
    return detector.calibrate_from_reference(image, reference_object, reference_size_cm)
