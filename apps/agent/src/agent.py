"""
Tuntun.In AI Mobility Companion Agent — entrypoint.

Dual-brain architecture:
- Reflex Layer: Gemini Live (instant audio-visual obstacle detection)
- Reasoning Layer: LangChain DeepAgents (multi-step route orchestration)

The implementation lives in the `tuntun_agent` package. This file wires up
logging, the AgentServer, and the per-room session handler. Logging is verbose
by design — configure level via LOG_LEVEL env var (default: INFO).

# ponytail: thin entrypoint only. All behavior is in tuntun_agent.* modules.
load_dotenv() runs before importing tuntun_agent so LOG_LEVEL is read from env.
"""

from __future__ import annotations

import time

from dotenv import load_dotenv

load_dotenv()  # must run before tuntun_agent imports (LOG_LEVEL read at import)

from livekit.agents import (  # noqa: E402
    AgentServer,
    AgentSession,
    JobContext,
    cli,
    room_io,
)

from tuntun_agent.agent import TuntunAgent  # noqa: E402
from tuntun_agent.convex import get_convex_client, ping_convex  # noqa: E402
from tuntun_agent.events import (  # noqa: E402
    attach_gps_handler,
    attach_room_event_loggers,
    attach_session_event_loggers,
)
from tuntun_agent.logging_setup import (  # noqa: E402
    get_logger,
    log_startup_env,
    setup_logging,
)

setup_logging()
log_startup_env()
logger = get_logger()

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

    # ── Attach verbose room event loggers ──
    # Logs every participant connect/disconnect, track publish/subscribe/fail,
    # and connection state change so we can see exactly whether the user's
    # mic/camera media ever reaches the agent.
    try:
        attach_room_event_loggers(ctx.room)
    except Exception as exc:
        logger.error("Failed to attach room event loggers: %s", exc, exc_info=True)

    # ── Convex connectivity check ──
    logger.info("Setting up Convex connection...")
    client = get_convex_client()
    if client:
        ping_convex(client, label="session_start")
    else:
        logger.warning(
            "Starting session without Convex — no DB persistence this session"
        )

    # ── Create and start agent session ──
    logger.info("Creating AgentSession...")
    t_session = time.monotonic()

    try:
        session = AgentSession(
            # Lower-latency turn handling:
            # - short aec_warmup_duration: less silence at session start
            # - aggressive endpointing: declare user turn done quickly
            # - preemptive generation: start drafting before turn fully ends
            aec_warmup_duration=0.5,
            turn_handling={
                "endpointing": {
                    "mode": "fixed",
                    "min_delay": 0.3,
                    "max_delay": 1.5,
                },
                "preemptive_generation": {
                    "enabled": True,
                    "preemptive_tts": True,
                },
            },
            # Deep Navigator origin: latest GPS fix published by the web client
            # via the LiveKit data channel (topic "gps"). Updated by the
            # data_received handler below; read by the navigate_to tool.
            userdata={"lat": None, "lng": None},
        )
        logger.info(
            "AgentSession created: elapsed=%.1fms "
            "(aec_warmup=0.5s, endpointing min=0.3s max=1.5s, preemptive=on)",
            (time.monotonic() - t_session) * 1000,
        )
    except Exception as exc:
        logger.error("Failed to create AgentSession: %s", exc, exc_info=True)
        raise

    # ── Attach verbose session event loggers ──
    # Logs user/agent state transitions, speech creation, transcription,
    # and per-turn metrics (TTFT, duration, token counts).
    try:
        attach_session_event_loggers(session)
    except Exception as exc:
        logger.error("Failed to attach session event loggers: %s", exc, exc_info=True)

    # ── Deep Navigator: receive GPS fixes from the web client ──
    # The web client publishes {type:"gps", lat, lng} on data topic "gps".
    # We store the latest fix on session.userdata so the navigate_to tool can
    # use it as the route origin.
    try:
        attach_gps_handler(ctx.room, session)
    except Exception as exc:
        logger.error("Failed to attach GPS handler: %s", exc, exc_info=True)

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
