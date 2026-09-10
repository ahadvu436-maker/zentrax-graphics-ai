# syntax=docker/dockerfile:1.7

# ============================================================================
# Zentrax AI — FastAPI backend
# Multi-stage build: compile deps in a full image, run in a slim one.
# Uses CUDA base image since torch/diffusers benefit from GPU inference.
# Swap the base images for plain python:3.11-slim if running CPU-only.
# ============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder — install dependencies into a virtualenv
# ---------------------------------------------------------------------------
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1 \
PIP_NO_CACHE_DIR=1 \
PIP_DISABLE_PIP_VERSION_CHECK=1

# System build deps (kept only in this stage — not in the final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
python3.11 \
python3.11-venv \
python3-pip \
build-essential \
git \
curl \
&& rm -rf /var/lib/apt/lists/*

# Isolated virtualenv keeps the final COPY clean and reproducible
RUN python3.11 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Leverage Docker layer caching — deps only reinstall when requirements.txt changes
COPY requirements.txt .
RUN pip install --upgrade pip && \
pip install -r requirements.txt \
--extra-index-url https://download.pytorch.org/whl/cu121

# ---------------------------------------------------------------------------
# Stage 2: Runtime — slim image, no compilers, no build cache
# ---------------------------------------------------------------------------
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1 \
PATH="/opt/venv/bin:$PATH" \
HF_HOME=/app/.cache/huggingface

# Only runtime system deps — no gcc/git/etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
python3.11 \
libgl1 \
libglib2.0-0 \
curl \
&& rm -rf /var/lib/apt/lists/*

# Non-root user — never run the app as root in production
RUN groupadd --gid 1000 zentrax && \
useradd --uid 1000 --gid zentrax --shell /bin/bash --create-home zentrax

# Bring in the prebuilt virtualenv from the builder stage
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Copy application code last — this is the layer that changes most often,
# so keeping it last maximizes cache hits on the (slow) dependency layers above.
COPY --chown=zentrax:zentrax ./app ./app

# Writable cache dir for downloaded model weights (mount a volume here in prod
# so models persist across container restarts instead of re-downloading)
RUN mkdir -p /app/.cache/huggingface && chown -R zentrax:zentrax /app/.cache

USER zentrax

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
CMD curl -f http://localhost:8000/health || exit 1

# --proxy-headers: correct client IPs behind a reverse proxy (nginx/ALB/etc.)
# --workers: keep at 1 per GPU container; scale via multiple container replicas,
# not multiple workers, since each worker would load its own copy
# of the model into GPU memory.
CMD ["uvicorn", "app.main:app", \
"--host", "0.0.0.0", \
"--port", "8000", \
"--proxy-headers", \
"--workers", "1"]