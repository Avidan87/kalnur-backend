"""
Depth Anything V2 Model Wrapper
High-accuracy monocular depth estimation using state-of-the-art architecture

Replaces MiDaS_small for improved boundary detection and depth accuracy.
Expected accuracy improvement: +15-20% over MiDaS_small
"""

import torch
import numpy as np
from PIL import Image
from typing import Optional, Union
import logging

logger = logging.getLogger(__name__)


class DepthAnythingV2:
    """
    Depth Anything V2 Small model wrapper with lazy loading and auto-unload

    Model: depth-anything/Depth-Anything-V2-Small-hf
    Parameters: 24.8M
    License: Apache 2.0
    """

    def __init__(self, device: str = "cpu", model_variant: str = "small"):
        """
        Initialize Depth Anything V2 model

        Args:
            device: "cpu" or "cuda" (Railway uses CPU)
            model_variant: "small", "base", "large" (only small is Apache 2.0)
        """
        self.device = device
        self.model_variant = model_variant
        self.model = None
        self.processor = None
        self._model_loaded = False

        # Model selection
        if model_variant == "small":
            self.model_name = "depth-anything/Depth-Anything-V2-Small-hf"
        elif model_variant == "base":
            self.model_name = "depth-anything/Depth-Anything-V2-Base-hf"
        elif model_variant == "large":
            self.model_name = "depth-anything/Depth-Anything-V2-Large-hf"
        else:
            raise ValueError(f"Invalid model variant: {model_variant}. Use 'small', 'base', or 'large'.")

    def load_model(self):
        """Lazy load model on first inference (saves memory)"""
        if self._model_loaded:
            return

        try:
            logger.info(f"Loading Depth Anything V2 ({self.model_variant})...")

            # Import here to avoid loading if not needed
            from transformers import AutoModelForDepthEstimation, AutoImageProcessor

            # Load model and processor directly (bypassing pipeline for speed)
            self.model = AutoModelForDepthEstimation.from_pretrained(self.model_name)
            self.processor = AutoImageProcessor.from_pretrained(self.model_name)

            # Move model to device
            if self.device == "cuda" and torch.cuda.is_available():
                self.model = self.model.to("cuda")
            else:
                self.model = self.model.to("cpu")

            self.model.eval()  # Set to evaluation mode

            self._model_loaded = True
            logger.info(f"✓ Depth Anything V2 ({self.model_variant}) loaded successfully (pipeline bypassed)")

        except Exception as e:
            logger.error(f"Failed to load Depth Anything V2: {e}")
            raise

    def predict(
        self,
        image: Union[np.ndarray, Image.Image],
        return_pil: bool = False
    ) -> Union[np.ndarray, Image.Image]:
        """
        Generate depth map from RGB image

        Args:
            image: RGB image as numpy array (H, W, 3) or PIL Image
            return_pil: If True, return PIL Image instead of numpy array

        Returns:
            Depth map as numpy array (H, W) or PIL Image
            - Values are relative inverse depth (0-1 normalized)
            - Higher values = closer to camera
        """
        # Ensure model is loaded
        self.load_model()

        # Convert numpy to PIL if needed
        if isinstance(image, np.ndarray):
            # Ensure RGB format
            if image.shape[-1] == 3:
                pil_image = Image.fromarray(image.astype(np.uint8))
            else:
                raise ValueError(f"Expected RGB image with shape (H, W, 3), got {image.shape}")
        else:
            pil_image = image

        # Run inference (manual preprocessing for speed)
        try:
            # Store original size for resizing back
            original_size = pil_image.size  # (width, height)

            # Preprocess image using the processor
            inputs = self.processor(images=pil_image, return_tensors="pt")

            # Move inputs to device
            if self.device == "cuda" and torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}

            # Run model inference (no_grad for speed)
            with torch.no_grad():
                outputs = self.model(**inputs)
                predicted_depth = outputs.predicted_depth

            # Post-process depth map
            # Interpolate to original image size
            prediction = torch.nn.functional.interpolate(
                predicted_depth.unsqueeze(1),
                size=(pil_image.size[1], pil_image.size[0]),  # (height, width)
                mode="bicubic",
                align_corners=False,
            )

            # Convert to numpy and normalize
            depth_map = prediction.squeeze().cpu().numpy()

            # Normalize to 0-1 range
            depth_min = depth_map.min()
            depth_max = depth_map.max()
            if depth_max - depth_min > 1e-6:  # Avoid division by zero
                depth_map = (depth_map - depth_min) / (depth_max - depth_min)
            else:
                depth_map = np.zeros_like(depth_map)

            # VERIFIED: Both Depth Anything V2 and MiDaS output INVERSE DEPTH
            # Sources:
            # - https://github.com/DepthAnything/Depth-Anything-V2/issues/93
            # - https://github.com/isl-org/MiDaS/issues/21
            # Convention: Higher value = closer to camera = food peaks
            # NO INVERSION NEEDED - both models use same convention!

            # Convert to float32
            depth_map = depth_map.astype(np.float32)

            if return_pil:
                # Convert back to PIL if requested
                depth_map_uint8 = (depth_map * 255).astype(np.uint8)
                return Image.fromarray(depth_map_uint8)

            logger.info(f"Depth map generated (inverse depth, higher=closer): shape={depth_map.shape}, range=[{depth_map.min():.3f}, {depth_map.max():.3f}]")

            return depth_map

        except Exception as e:
            logger.error(f"Depth prediction failed: {e}")
            raise

    def unload_model(self):
        """Free memory by unloading model"""
        if self._model_loaded:
            del self.model
            self.model = None
            self._model_loaded = False

            # Clear CUDA cache if using GPU
            if self.device == "cuda" and torch.cuda.is_available():
                torch.cuda.empty_cache()

            logger.info(f"✓ Depth Anything V2 ({self.model_variant}) unloaded from memory")

    def is_loaded(self) -> bool:
        """Check if model is currently loaded in memory"""
        return self._model_loaded

    def get_model_info(self) -> dict:
        """Get information about the loaded model"""
        return {
            "model_name": self.model_name,
            "variant": self.model_variant,
            "device": self.device,
            "loaded": self._model_loaded,
            "parameters": "24.8M" if self.model_variant == "small" else "Unknown"
        }


# Convenience function for simple usage
def estimate_depth(
    image: Union[np.ndarray, Image.Image],
    device: str = "cpu",
    model_variant: str = "small"
) -> np.ndarray:
    """
    One-shot depth estimation (loads model, predicts, unloads)

    Args:
        image: RGB image (numpy array or PIL Image)
        device: "cpu" or "cuda"
        model_variant: "small", "base", or "large"

    Returns:
        Depth map as numpy array (H, W)
    """
    model = DepthAnythingV2(device=device, model_variant=model_variant)
    depth_map = model.predict(image)
    model.unload_model()
    return depth_map


# Test function
if __name__ == "__main__":
    """Test Depth Anything V2 wrapper"""

    print("Testing Depth Anything V2 Wrapper\n")

    # Create test image
    print("1. Creating test image...")
    test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    print(f"   Test image shape: {test_image.shape}\n")

    # Initialize model
    print("2. Initializing Depth Anything V2 (small)...")
    model = DepthAnythingV2(device="cpu", model_variant="small")
    print(f"   Model info: {model.get_model_info()}\n")

    # Generate depth map
    print("3. Generating depth map...")
    depth_map = model.predict(test_image)
    print(f"   ✓ Depth map generated")
    print(f"   Shape: {depth_map.shape}")
    print(f"   Dtype: {depth_map.dtype}")
    print(f"   Range: [{depth_map.min():.3f}, {depth_map.max():.3f}]\n")

    # Validate output
    print("4. Validating output...")
    assert depth_map.shape == (480, 640), f"Unexpected shape: {depth_map.shape}"
    assert depth_map.dtype in [np.float32, np.float64], f"Unexpected dtype: {depth_map.dtype}"
    assert 0 <= depth_map.min() <= 1, f"Unexpected min value: {depth_map.min()}"
    assert 0 <= depth_map.max() <= 1, f"Unexpected max value: {depth_map.max()}"
    print("   ✓ All validations passed\n")

    # Test unload
    print("5. Testing model unload...")
    model.unload_model()
    print(f"   Model loaded: {model.is_loaded()}\n")

    print("✅ All tests passed! Depth Anything V2 wrapper is working correctly.\n")
