"""
Tuntun.In AI Mobility Companion Agent

Dual-brain architecture:
- Reflex Layer: Gemini Live (instant audio-visual obstacle detection)
- Reasoning Layer: LangChain DeepAgents (multi-step route orchestration)

Logging is verbose by design — every lifecycle event, tool call, error, and
state transition is logged to aid debugging during development and production.
Configure level via LOG_LEVEL env var (default: INFO).
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from livekit.agents import (  # noqa: E402
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    cli,
    room_io,
)
from livekit.plugins import google  # noqa: E402

# ─── Logging Setup ──────────────────────────────────────────────────────────
# Verbose logging for maximum debuggability. Every module, every lifecycle
# event, every error gets logged with context.

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d — %(message)s"

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

logger = logging.getLogger("tuntun.agent")

# Log startup environment state (redact secrets)
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


# ─── Convex Integration ────────────────────────────────────────────────────
# ponytail: ConvexClient instantiated per-call to avoid threading issues.
# Each session gets its own client; no global state.


def _get_convex_client() -> Any | None:
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


def _ping_convex(client: Any, label: str = "startup") -> bool:
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


# ─── Agent Definition ──────────────────────────────────────────────────────


class TuntunAgent(Agent):
    """
    Reflex Layer: uses Gemini Live for instant multimodal responses.
    Receives live camera frames + user audio → spatial audio warnings.
    """

    def __init__(self) -> None:
        model_name = "gemini-2.5-flash-native-audio-preview-12-2025"
        voice = "Puck"

        logger.info("TuntunAgent.__init__ — creating Gemini Live model")
        logger.info("  model: %s", model_name)
        logger.info("  voice: %s", voice)
        logger.info("  temperature: 0.8")

        try:
            llm = google.realtime.RealtimeModel(
                model=model_name,
                voice=voice,
                temperature=0.8,
            )
            logger.info("Gemini Live model created successfully")
        except Exception as exc:
            logger.error("Failed to create Gemini Live model: %s", exc, exc_info=True)
            raise

        super().__init__(
            instructions=(
                "You are Tuntun, a multimodal AI mobility companion for visually impaired users. "
                "Watch the smartphone camera feed and warn the user about street obstacles: "
                "parked motorcycles, open manholes, low-hanging banners, potholes, construction barriers. "
                "Keep warnings short, spatial (left/center/right), and urgent. "
                "Speak in Indonesian (Bahasa Indonesia) by default unless user speaks English."
            ),
            llm=llm,
        )
        logger.info("TuntunAgent initialized — instructions set, LLM wired")

    async def on_enter(self) -> None:
        """Called when agent enters the room and is ready to interact."""
        logger.info("TuntunAgent.on_enter — agent joined the room")
        logger.info("  Generating greeting reply...")

        try:
            t0 = time.monotonic()
            await self.session.generate_reply(
                instructions=(
                    "Greet the user briefly and tell them you are watching for obstacles."
                )
            )
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info("Greeting generated successfully: elapsed=%.1fms", elapsed_ms)
        except Exception as exc:
            logger.error("Failed to generate greeting: %s", exc, exc_info=True)
            raise

    async def on_exit(self) -> None:
        """Called when agent is leaving the room."""
        logger.info("TuntunAgent.on_exit — agent leaving room")


# ─── Server + Session Handler ──────────────────────────────────────────────

server = AgentServer()
logger.info("AgentServer created")


@server.rtc_session(agent_name="tuntun-agent")
async def entrypoint(ctx: JobContext) -> None:
    """
    Handle a new room session.

    Flow:
    1. Log session start with room metadata
    2. Ping Convex to verify DB connectivity
    3. Create AgentSession with video+audio I/O
    4. Start the TuntunAgent
    """
    t_start = time.monotonic()

    logger.info("=" * 60)
    logger.info("NEW SESSION — room=%s", ctx.room.name)
    logger.info("  job_id=%s", getattr(ctx, "job_id", "<unknown>"))
    logger.info("  agent_name=tuntun-agent")

    # ── Convex connectivity check ──
    logger.info("Setting up Convex connection...")
    client = _get_convex_client()
    if client:
        _ping_convex(client, label="session_start")
    else:
        logger.warning(
            "Starting session without Convex — no DB persistence this session"
        )

    # ── Create and start agent session ──
    logger.info("Creating AgentSession...")
    t_session = time.monotonic()

    try:
        session = AgentSession()
        logger.info(
            "AgentSession created: elapsed=%.1fms",
            (time.monotonic() - t_session) * 1000,
        )
    except Exception as exc:
        logger.error("Failed to create AgentSession: %s", exc, exc_info=True)
        raise

    # ── Configure room I/O ──
    logger.info(
        "Configuring room I/O — video_input=True audio_input=True audio_output=True"
    )
    room_options = room_io.RoomOptions(
        video_input=True,
        audio_input=True,
        audio_output=True,
    )

    # ── Start the agent ──
    logger.info("Starting TuntunAgent in room...")
    t_start_call = time.monotonic()

    try:
        await session.start(
            agent=TuntunAgent(),
            room=ctx.room,
            room_options=room_options,
        )
        elapsed_ms = (time.monotonic() - t_start_call) * 1000
        logger.info("AgentSession.start() completed: elapsed=%.1fms", elapsed_ms)
    except Exception as exc:
        logger.error("AgentSession.start() failed: %s", exc, exc_info=True)
        raise

    total_ms = (time.monotonic() - t_start) * 1000
    logger.info(
        "Session setup complete: total_elapsed=%.1fms room=%s",
        total_ms,
        ctx.room.name,
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    logger.info("Starting Tuntun agent CLI...")
    cli.run_app(server)
