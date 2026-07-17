# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install deps (cached layer). --extra wakeword installs openwakeword + onnxruntime
# (optional extra in pyproject.toml). Without it, wake-word gating silently
# disables at runtime with ModuleNotFoundError.
COPY apps/agent/pyproject.toml apps/agent/uv.lock* ./
RUN --mount=type=cache,id=s/c44e7315-4976-4cb6-8278-9f0ac1e7cc60-/root/.cache/uv,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --extra wakeword

# Copy source
COPY apps/agent/src/ ./src/

# Install project
RUN --mount=type=cache,id=s/c44e7315-4976-4cb6-8278-9f0ac1e7cc60-/root/.cache/uv,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra wakeword

# Bake openwakeword preprocessor ONNX models (melspectrogram + embedding) into
# the image. openwakeword ships them out-of-wheel and downloads them on first
# use at runtime; in Railway that first-use download is slow / fragile. Doing
# it here in the build means the resources/models dir is populated and
# HeyTutuDetector._ensure_preprocessor_models finds them present and skips.
RUN uv run python -c "from openwakeword.utils import download_models; download_models()"

# Production stage
FROM python:3.12-slim AS production

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

COPY --from=base --chown=appuser:appuser /app /app

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "python", "src/agent.py", "start"]
