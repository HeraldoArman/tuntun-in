"""Logging configuration + startup environment banner.

Logging is verbose by design — every lifecycle event, tool call, error, and
state transition is logged to aid debugging. Configure level via LOG_LEVEL
(default: INFO).
"""

from __future__ import annotations

import logging
import os
import sys

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d — %(message)s"

# Shared logger name — preserves the original `tuntun.agent:lineno` output
# across all modules.
LOGGER_NAME = "tuntun.agent"


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """Return a logger under the shared tuntun.agent namespace."""
    return logging.getLogger(name)


def setup_logging() -> None:
    """Configure root logging. Verbose by design for debuggability."""
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=LOG_FORMAT,
        stream=sys.stdout,
        force=True,
    )

    # Enable debug logging for key libraries if LOG_LEVEL=DEBUG
    if LOG_LEVEL == "DEBUG":
        for lib in [
            "livekit",
            "livekit.agents",
            "livekit.rtc",
            "convex",
            "google",
            "google.genai",
            "httpx",
            "websockets",
        ]:
            logging.getLogger(lib).setLevel(logging.DEBUG)


def log_startup_env() -> None:
    """Log startup environment state (secrets redacted)."""
    logger = get_logger()
    logger.info("=" * 60)
    logger.info("Tuntun.In Agent — starting up")
    logger.info("Python: %s", sys.version)
    logger.info("Log level: %s", LOG_LEVEL)
    logger.info("LIVEKIT_URL: %s", os.environ.get("LIVEKIT_URL", "<not set>"))
    logger.info("CONVEX_URL: %s", os.environ.get("CONVEX_URL", "<not set>"))
    logger.info(
        "GOOGLE_API_KEY: %s",
        "set" if os.environ.get("GOOGLE_API_KEY") else "<not set>",
    )
    logger.info(
        "CONVEX_SERVICE_SECRET: %s",
        "set" if os.environ.get("CONVEX_SERVICE_SECRET") else "<not set>",
    )
    logger.info("=" * 60)
