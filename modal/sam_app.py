"""
SAM 2 Food Segmentation - Modal GPU Endpoint

Replaces the local synchronous SAM 2 call in vision_agent.py (which blocks
the async event loop and runs on HF Spaces CPU for 30-60s) with a fast
async HTTP call to this Modal GPU endpoint (~1-2s on T4).

Deploy:
    modal deploy modal/sam_app.py

Endpoint:
    POST /segment
        Body:  { "image_base64": "<str>", "food_names": ["Jollof Rice", ...] }
        Returns: { "masks": { "Jollof Rice": [[bool,...], ...], ... } }

The masks are returned as nested lists of booleans (JSON-serialisable),
matching the shape (H, W) for each food name.
"""

import modal

# ---------------------------------------------------------------------------
# Modal image
# ---------------------------------------------------------------------------
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")  # Required to install SAM 2 from GitHub
    .pip_install(
        "torch>=2.0.0",
        "torchvision>=0.15.0",
        "numpy>=1.24.0,<2.0.0",
        "pillow>=10.0.0",
        "opencv-contrib-python-headless>=4.8.0",
        "scikit-learn>=1.3.0",
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "pydantic>=2.0.0",
        # SAM 2 from Meta's GitHub
        "git+https://github.com/facebookresearch/segment-anything-2.git",
    )
)

# Modal volume to cache the SAM 2 checkpoint (avoids re-downloading on every cold start)
sam_volume = modal.Volume.from_name("kai-sam2-weights", create_if_missing=True)

app = modal.App("kai-sam-segmentation", image=image)

# ---------------------------------------------------------------------------
# Download SAM 2 weights into the volume (run once)
# ---------------------------------------------------------------------------
@app.function(
    image=image,
    volumes={"/weights": sam_volume},
    timeout=300,
)
def download_weights():
    """
    Download SAM 2 small checkpoint into the persistent Modal volume.
    Run once with: modal run modal/sam_app.py::download_weights
    """
    import os
    import urllib.request

    weights_dir = "/weights/sam2"
    os.makedirs(weights_dir, exist_ok=True)

    checkpoint_path = f"{weights_dir}/sam2_hiera_small.pt"
    if os.path.exists(checkpoint_path):
        print(f"✓ Checkpoint already exists: {checkpoint_path}")
        return

    url = "https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_small.pt"
    print(f"Downloading SAM 2 small from {url} ...")
    urllib.request.urlretrieve(url, checkpoint_path)
    print(f"✓ Downloaded to {checkpoint_path}")
    sam_volume.commit()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
def build_fastapi_app():
    """Build the SAM 2 FastAPI app. Runs inside the Modal container."""

    import base64
    import io
    import logging
    import os

    import numpy as np
    import torch
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from PIL import Image
    from pydantic import BaseModel
    from typing import List

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info(f"SAM 2 endpoint using device: {device}")

    # Model state — loaded once per container lifetime via @modal.enter equivalent
    _model = None
    _predictor = None

    def get_model():
        nonlocal _model, _predictor
        if _model is not None:
            return _model, _predictor

        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        checkpoint = "/weights/sam2/sam2_hiera_small.pt"
        config = "configs/sam2/sam2_hiera_s.yaml"

        logger.info("Loading SAM 2 small onto GPU...")
        _model = build_sam2(config, checkpoint, device=device)
        _predictor = SAM2ImagePredictor(_model)
        logger.info("✓ SAM 2 loaded")
        return _model, _predictor

    web_app = FastAPI(
        title="SAM 2 Food Segmentation - Modal GPU",
        version="1.0.0"
    )

    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Pydantic models
    # ------------------------------------------------------------------

    class SegmentRequest(BaseModel):
        image_base64: str
        food_names: List[str]

    class SegmentResponse(BaseModel):
        # food_name -> (H, W) boolean mask as nested list
        masks: dict
        success: bool
        message: str

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def decode_base64_image(b64: str) -> np.ndarray:
        if "," in b64 and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        return np.array(img)

    def segment(image: np.ndarray, food_names: List[str]) -> dict:
        """
        Run SAM 2 automatic mask generation and assign masks to food names
        by area order (largest mask → first food name, etc.).
        Mirrors the logic in kai/agents/sam_segmentation.py exactly.
        """
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator

        model, _ = get_model()

        # CPU-optimised settings kept identical to the original sam_segmentation.py
        mask_generator = SAM2AutomaticMaskGenerator(
            model,
            points_per_side=12,
            pred_iou_thresh=0.80,
            stability_score_thresh=0.88,
            crop_n_layers=0,
            crop_n_points_downscale_factor=2,
            min_mask_region_area=500,
        )

        logger.info("Running SAM 2 automatic segmentation...")
        masks = mask_generator.generate(image)
        logger.info(f"✓ Generated {len(masks)} candidate masks")

        # Sort by area descending — same as original
        masks = sorted(masks, key=lambda x: x["area"], reverse=True)

        food_masks = {}
        h, w = image.shape[:2]

        for idx, food_name in enumerate(food_names):
            if idx < len(masks):
                mask = masks[idx]["segmentation"]  # (H, W) bool
                food_masks[food_name] = mask.tolist()  # JSON-serialisable
                logger.info(
                    f"✓ {food_name}: {masks[idx]['area']} px "
                    f"({masks[idx]['area'] / (h * w):.1%} of image)"
                )
            else:
                logger.warning(f"⚠️ No mask for {food_name}, returning empty")
                food_masks[food_name] = np.zeros((h, w), dtype=bool).tolist()

        return food_masks

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @web_app.get("/health")
    async def health():
        return JSONResponse(status_code=200, content={
            "status": "healthy",
            "service": "SAM 2 Food Segmentation - Modal GPU",
            "device": device,
        })

    @web_app.post("/segment", response_model=SegmentResponse)
    async def segment_endpoint(request: SegmentRequest):
        if not request.image_base64:
            raise HTTPException(status_code=400, detail="image_base64 required")
        if not request.food_names:
            raise HTTPException(status_code=400, detail="food_names required")

        try:
            image = decode_base64_image(request.image_base64)
            masks = segment(image, request.food_names)
            return SegmentResponse(
                masks=masks,
                success=True,
                message=f"Segmented {len(masks)} foods"
            )
        except Exception as e:
            logger.error(f"Segmentation error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return web_app


# ---------------------------------------------------------------------------
# Modal ASGI endpoint — T4 GPU, SAM weights volume mounted
# ---------------------------------------------------------------------------
@app.function(
    gpu="T4",
    image=image,
    volumes={"/weights": sam_volume},
    scaledown_window=60,    # Stay warm 1 min after last request
    timeout=60,             # SAM on GPU should finish well within 60s
)
@modal.asgi_app()
def fastapi_app():
    return build_fastapi_app()
