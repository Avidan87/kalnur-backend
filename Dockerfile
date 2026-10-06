# ============================================================================
# KAI - Nigerian Nutrition AI Backend
# Dockerfile for Hugging Face Spaces (Docker SDK, CPU Basic)
# ============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (OpenCV, PyTorch, git for SAM 2, curl for model download)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Install SAM 2 from GitHub (retry up to 3 times on network failure)
RUN pip install git+https://github.com/facebookresearch/segment-anything-2.git || \
    pip install git+https://github.com/facebookresearch/segment-anything-2.git || \
    pip install git+https://github.com/facebookresearch/segment-anything-2.git

# Copy application code
COPY kai/ ./kai/

# Download SAM 2 model checkpoint (176MB) - not in git due to size
RUN mkdir -p models/sam2 && \
    curl -L --retry 5 --retry-delay 3 --retry-connrefused \
    -o models/sam2/sam2_hiera_small.pt \
    https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_small.pt

# Copy knowledge base (JSONL food data)
COPY knowledge-base/ ./knowledge-base/

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV TORCH_HOME=/tmp/torch_cache
ENV PORT=7860

# HF Spaces requires port 7860
EXPOSE 7860

# Start FastAPI server
CMD ["python", "-m", "uvicorn", "kai.api.server:app", "--host", "0.0.0.0", "--port", "7860", "--log-level", "info"]
