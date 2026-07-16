"""Convex DB connectivity (best-effort).

# ponytail: ConvexClient instantiated per-call to avoid threading issues.
Each session gets its own client; no global state. Failures degrade to
"no DB persistence" rather than crashing the session.
"""

from __future__ import annotations

import os
import time
from typing import Any

from tuntun_agent.logging_setup import get_logger

logger = get_logger()


def get_convex_client() -> Any | None:
    """Create a Convex client. Returns None if CONVEX_URL not configured."""
    from convex import ConvexClient

    url = os.environ.get("CONVEX_URL", "")
    if not url:
        logger.warning(
            "CONVEX_URL not set — Convex integration disabled. "
            "Agent will run without DB persistence."
        )
        return None

    logger.info("Creating ConvexClient: url=%s", url)
    try:
        client = ConvexClient(url)
        logger.info("ConvexClient created successfully")
        return client
    except Exception as exc:
        logger.error(
            "Failed to create ConvexClient: %s — agent will run without DB",
            exc,
            exc_info=True,
        )
        return None


def ping_convex(client: Any, label: str = "startup") -> bool:
    """Ping Convex to verify connectivity. Returns True on success."""
    if not client:
        logger.debug("Convex ping skipped (no client): label=%s", label)
        return False

    secret = os.environ.get("CONVEX_SERVICE_SECRET", "")
    if not secret:
        logger.warning(
            "CONVEX_SERVICE_SECRET not set — Convex ping will fail: label=%s",
            label,
        )
        return False

    t0 = time.monotonic()
    try:
        logger.info("Convex ping start: label=%s", label)
        result = client.mutation("agent:ping", {"secret": secret})
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Convex ping success: label=%s result=%s elapsed=%.1fms",
            label,
            result,
            elapsed_ms,
        )
        return True
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.error(
            "Convex ping failed: label=%s elapsed=%.1fms error=%s",
            label,
            elapsed_ms,
            exc,
            exc_info=True,
        )
        return False
