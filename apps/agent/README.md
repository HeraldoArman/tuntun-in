# Tuntun.In Agent

Python LiveKit agent for the Tuntun.In multimodal AI mobility companion.

## Setup

```bash
# Install dependencies
uv sync

# Copy env template
cp .env.example .env
# Edit .env with your credentials

# Dev mode (waits for frontend connection)
uv run python src/agent.py dev

# Terminal test (no LiveKit needed)
uv run python src/agent.py console

# Production
uv run python src/agent.py start
```

## Lint & Test

```bash
uv run ruff check .
uv run ruff format .
uv run pytest
```
