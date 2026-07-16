# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install deps (cached layer)
COPY apps/agent/pyproject.toml apps/agent/uv.lock* ./
RUN --mount=type=cache,id=cacheKey:c44e7315-4976-4cb6-8278-9f0ac1e7cc60,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source
COPY apps/agent/src/ ./src/

# Install project
RUN --mount=type=cache,id=cacheKey:c44e7315-4976-4cb6-8278-9f0ac1e7cc60,target=/root/.cache/uv \
    uv sync --frozen --no-dev

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
