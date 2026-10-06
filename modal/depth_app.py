"""
Depth Anything V2 - Modal GPU Endpoint

Replaces the Railway CPU microservice with a Modal serverless GPU function.
Exposes the same API shape as the old Railway server so depth_estimation_client.py
needs zero logic changes — just swap the DEPTH_ESTIMATION_URL env var.

Deploy:
    modal deploy modal/depth_app.py

Endpoints (same as Railway):
    POST /api/v1/portion/estimate   - single food portion
    POST /api/v1/portion/batch      - multiple foods in one call (primary path)
    POST /api/v1/depth/estimate     - raw depth map
    GET  /health                    - health check
"""

import modal

# ---------------------------------------------------------------------------
# Modal image — install all dependencies the model needs
# ---------------------------------------------------------------------------
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch>=2.0.0",
        "torchvision>=0.15.0",
        "timm>=0.9.0",
        "transformers>=4.35.0",
        "opencv-contrib-python-headless>=4.8.0",
        "pillow>=10.0.0",
        "numpy>=1.24.0,<2.0.0",
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "pydantic>=2.0.0",
        "requests>=2.31.0",
    )
    # Mount all local logic files into the container
    .add_local_file("modal/depth_anything_v2.py", "/app/depth_anything_v2.py")
    .add_local_file("modal/portion_calculator.py", "/app/portion_calculator.py")
    .add_local_file("modal/reference_detector.py", "/app/reference_detector.py")
    .add_local_file("modal/nigerian_food_densities.py", "/app/nigerian_food_densities.py")
    .add_local_file("modal/nigerian_food_heights.py", "/app/nigerian_food_heights.py")
    .add_local_file("modal/nigerian_food_priors.py", "/app/nigerian_food_priors.py")
    .add_local_file("modal/depth_refinement.py", "/app/depth_refinement.py")
    .add_local_file("knowledge-base/data/processed/nigerian_foods_v2_improved.jsonl", "/app/nigerian_foods_v2_improved.jsonl")
)

# Persistent volume to cache Depth Anything V2 weights — avoids re-downloading on every cold start
depth_volume = modal.Volume.from_name("kai-depth-weights", create_if_missing=True)

app = modal.App("kai-depth-estimation", image=image)


# ---------------------------------------------------------------------------
# Download Depth Anything V2 weights into the volume (run once)
# ---------------------------------------------------------------------------
@app.function(
    image=image,
    volumes={"/weights": depth_volume},
    timeout=300,
)
def download_weights():
    """
    Download Depth Anything V2 Small weights from HuggingFace into the
    persistent Modal volume so cold starts don't re-download every time.

    Run once with: modal run modal/depth_app.py::download_weights
    """
    from transformers import AutoModelForDepthEstimation, AutoImageProcessor

    model_name = "depth-anything/Depth-Anything-V2-Small-hf"
    save_dir = "/weights/depth_anything_v2_small"

    import os
    if os.path.exists(save_dir) and os.listdir(save_dir):
        print(f"✓ Weights already cached at {save_dir}")
        return

    print(f"Downloading {model_name} to {save_dir} ...")
    AutoModelForDepthEstimation.from_pretrained(model_name).save_pretrained(save_dir)
    AutoImageProcessor.from_pretrained(model_name).save_pretrained(save_dir)
    depth_volume.commit()
    print(f"✓ Weights cached at {save_dir}")

# ---------------------------------------------------------------------------
# FastAPI app — identical endpoints to the old Railway server
# ---------------------------------------------------------------------------

def build_fastapi_app():
    """Build the FastAPI app with all endpoints. Runs inside the Modal container."""

    import sys
    sys.path.insert(0, "/app")

    import base64
    import io
    import logging
    import time
    import gc
    import asyncio
    from datetime import datetime

    import numpy as np
    import torch
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from PIL import Image
    from pydantic import BaseModel
    from typing import Optional

    from depth_anything_v2 import DepthAnythingV2
    from depth_refinement import refine_depth_with_color, iterative_refinement
    from portion_calculator import estimate_portion_from_depth, PortionCalculator
    from reference_detector import ReferenceObjectDetector
    from nigerian_food_densities import estimate_weight_from_volume
    from nigerian_food_priors import NigerianFoodPriors

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # Model state — loaded once per container lifetime
    depth_model = None
    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"Using device: {device}")

    web_app = FastAPI(
        title="Depth Anything V2 - Modal GPU",
        description="Depth estimation for KAI portion calculation (Modal GPU)",
        version="2.0.0"
    )

    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Pydantic models (same shape as Railway server)
    # ------------------------------------------------------------------

    class DepthRequest(BaseModel):
        image_url: Optional[str] = None
        image_base64: Optional[str] = None

    class DepthResponse(BaseModel):
        depth_map_shape: tuple
        min_depth: float
        max_depth: float
        mean_depth: float
        success: bool
        message: str

    class PortionRequest(BaseModel):
        image_url: Optional[str] = None
        image_base64: Optional[str] = None
        food_type: Optional[str] = None
        reference_object: Optional[str] = None
        reference_size_cm: Optional[float] = None

    class PortionEstimate(BaseModel):
        portion_grams: float
        volume_ml: float
        confidence: float
        reference_object_detected: bool
        success: bool
        message: str

    class BatchPortionRequest(BaseModel):
        image_url: Optional[str] = None
        image_base64: Optional[str] = None
        bboxes: list[list[int]]
        food_types: list[str]
        reference_object: Optional[str] = None
        reference_size_cm: Optional[float] = None

    class BatchPortionResult(BaseModel):
        portion_grams: float
        volume_ml: float
        confidence: float
        food_type: str
        bbox: list[int]
        reference_object_detected: bool

    class BatchPortionResponse(BaseModel):
        results: list[BatchPortionResult]
        success: bool
        message: str
        total_processing_time: float

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_model():
        """Return loaded model, initialising on first call from cached volume weights."""
        nonlocal depth_model
        if depth_model is None:
            logger.info("Loading Depth Anything V2 Small from cached volume...")
            # Load from volume (fast — no network download)
            depth_model = DepthAnythingV2(device=device, model_variant="small")
            # Override model_name to point to the volume cache
            depth_model.model_name = "/weights/depth_anything_v2_small"
            depth_model.load_model()
            logger.info("✓ Model loaded from volume")
        return depth_model

    def decode_base64_image(b64: str) -> Image.Image:
        if "," in b64 and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")

    def run_depth(image: Image.Image) -> np.ndarray:
        model = get_model()
        img_array = np.array(image)
        raw_depth = model.predict(img_array)
        refined = refine_depth_with_color(raw_depth, img_array)
        final = iterative_refinement(refined, img_array, iterations=2)
        return final

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @web_app.get("/health")
    async def health():
        return JSONResponse(status_code=200, content={
            "status": "healthy",
            "service": "Depth Anything V2 - Modal GPU",
            "device": device,
        })

    @web_app.get("/")
    async def root():
        return {"service": "Depth Anything V2 Modal GPU", "status": "running"}

    @web_app.post("/api/v1/depth/estimate", response_model=DepthResponse)
    async def estimate_depth_endpoint(request: DepthRequest):
        if not request.image_base64:
            raise HTTPException(status_code=400, detail="image_base64 required")
        try:
            image = decode_base64_image(request.image_base64)
            depth_map = run_depth(image)
            return DepthResponse(
                depth_map_shape=depth_map.shape,
                min_depth=float(depth_map.min()),
                max_depth=float(depth_map.max()),
                mean_depth=float(depth_map.mean()),
                success=True,
                message="Depth estimation completed"
            )
        except Exception as e:
            logger.error(f"Depth estimation error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @web_app.post("/api/v1/portion/estimate", response_model=PortionEstimate)
    async def estimate_portion_endpoint(request: PortionRequest):
        if not request.image_base64:
            raise HTTPException(status_code=400, detail="image_base64 required")
        try:
            image = decode_base64_image(request.image_base64)
            depth_map = run_depth(image)
            img_array = np.array(image)
            result = estimate_portion_from_depth(
                image=img_array,
                depth_map=depth_map,
                food_type=request.food_type,
                reference_object=request.reference_object
            )
            return PortionEstimate(
                portion_grams=result["weight_grams"],
                volume_ml=result["volume_ml"],
                confidence=result["confidence"],
                reference_object_detected=result["reference_detected"],
                success=True,
                message=f"Portion estimated. Pixels: {result['food_pixels']}"
            )
        except Exception as e:
            logger.error(f"Portion estimation error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @web_app.post("/api/v1/portion/batch", response_model=BatchPortionResponse)
    async def estimate_portions_batch_endpoint(request: BatchPortionRequest):
        batch_start = time.perf_counter()

        if not request.image_base64:
            raise HTTPException(status_code=400, detail="image_base64 required")
        if not request.bboxes or not request.food_types:
            raise HTTPException(status_code=400, detail="bboxes and food_types required")
        if len(request.bboxes) != len(request.food_types):
            raise HTTPException(status_code=400, detail="bboxes and food_types length mismatch")

        try:
            image = decode_base64_image(request.image_base64)
            img_array = np.array(image)
            img_height, img_width = img_array.shape[:2]

            # Step 1: Depth once for the whole image
            logger.info(f"Batch: running depth on full image for {len(request.bboxes)} foods")
            depth_map = run_depth(image)

            # Step 2: Detect reference object once (shared calibration)
            ref_detector = ReferenceObjectDetector()
            calibration_info = ref_detector.calibrate_from_reference(
                image=img_array,
                reference_object=request.reference_object,
                reference_size_cm=request.reference_size_cm
            )
            reference_detected = calibration_info["detected"]
            pixel_to_cm_ratio = calibration_info["pixel_to_cm_ratio"]

            # Step 3: Process each food bbox
            results = []
            prior_engine = NigerianFoodPriors()

            for bbox, food_type in zip(request.bboxes, request.food_types):
                try:
                    x1, y1, x2, y2 = bbox
                    # Clamp to image bounds
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(img_width, x2), min(img_height, y2)

                    if x2 <= x1 or y2 <= y1:
                        results.append(BatchPortionResult(
                            portion_grams=200.0, volume_ml=150.0, confidence=0.5,
                            food_type=food_type, bbox=bbox, reference_object_detected=False
                        ))
                        continue

                    food_depth = depth_map[y1:y2, x1:x2]
                    food_image = img_array[y1:y2, x1:x2]

                    calculator = PortionCalculator()
                    calculator.pixel_to_cm_ratio = pixel_to_cm_ratio
                    calculator.reference_detected = reference_detected
                    calculator.calibration_confidence = calibration_info["confidence"]

                    food_mask, _ = calculator.detect_food_region(food_image, food_depth)
                    enhanced_depth = prior_engine.apply_shape_prior(food_depth, food_mask, food_type) if food_type else food_depth
                    food_mask, _ = calculator.detect_food_region(food_image, enhanced_depth)

                    volume_ml = calculator.calculate_volume_from_depth(
                        enhanced_depth, food_mask, calculator.pixel_to_cm_ratio, food_type=food_type
                    )
                    weight_grams = estimate_weight_from_volume(volume_ml, food_type) if food_type else volume_ml * 0.90

                    confidence = calibration_info["confidence"] if reference_detected else 0.3
                    if np.sum(food_mask) > (food_mask.size * 0.1):
                        confidence += 0.1
                    if food_type:
                        confidence += 0.1
                    confidence = min(confidence, 0.85)

                    results.append(BatchPortionResult(
                        portion_grams=float(weight_grams),
                        volume_ml=float(volume_ml),
                        confidence=float(confidence),
                        food_type=food_type,
                        bbox=bbox,
                        reference_object_detected=reference_detected
                    ))
                    logger.info(f"  ✓ {food_type}: {weight_grams:.0f}g (conf={confidence:.2f})")

                except Exception as e:
                    logger.error(f"Error on {food_type}: {e}")
                    results.append(BatchPortionResult(
                        portion_grams=200.0, volume_ml=150.0, confidence=0.5,
                        food_type=food_type, bbox=bbox, reference_object_detected=False
                    ))

            total_elapsed = time.perf_counter() - batch_start
            total_grams = sum(r.portion_grams for r in results)
            logger.info(f"Batch done: {len(results)} foods, {total_grams:.0f}g total, {total_elapsed:.2f}s")

            return BatchPortionResponse(
                results=results,
                success=True,
                message=f"{len(results)} foods processed in {total_elapsed:.2f}s",
                total_processing_time=total_elapsed
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Batch error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return web_app


# ---------------------------------------------------------------------------
# Modal ASGI endpoint — T4 GPU, stays warm for 10 min after last request
# ---------------------------------------------------------------------------
@app.function(
    gpu="T4",
    image=image,
    volumes={"/weights": depth_volume},  # Mount cached weights
    scaledown_window=60,                 # Stay warm 1 min after last request
    timeout=30,                          # Max 30s per request
)
@modal.asgi_app()
def fastapi_app():
    return build_fastapi_app()
