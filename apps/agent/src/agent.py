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

from google.genai import types as genai_types  # noqa: E402
from livekit.agents import (  # noqa: E402
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    cli,
    room_io,
)
from livekit.agents.metrics import RealtimeModelMetrics  # noqa: E402
from livekit.plugins import google  # noqa: E402

# Track source names (matching livekit TrackSource proto enum values)
_TRACK_SOURCE_NAMES = {
    0: "UNKNOWN",
    1: "CAMERA",
    2: "MICROPHONE",
    3: "SCREEN_SHARE",
    4: "SCREEN_SHARE_AUDIO",
}
_TRACK_KIND_NAMES = {0: "AUDIO", 1: "VIDEO", 2: "DATA"}


def _track_source_name(source: Any) -> str:
    """Human-readable track source name from a proto enum value."""
    return _TRACK_SOURCE_NAMES.get(int(source), f"UNKNOWN({source})")


def _track_kind_name(kind: Any) -> str:
    """Human-readable track kind name from a proto enum value."""
    return _TRACK_KIND_NAMES.get(int(kind), f"UNKNOWN({kind})")


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
        logger.info(
            "  latency tuning: realtime_input_config (aggressive VAD), english default"
        )

        try:
            llm = google.realtime.RealtimeModel(
                model=model_name,
                voice=voice,
                temperature=0.8,
                # Lower-latency Gemini Live VAD config:
                # - end_of_speech HIGH: declare turn done quickly after silence
                # - short silence_duration_ms: less waiting before end-of-speech
                # - short prefix_padding_ms: less padding before start-of-speech
                realtime_input_config=genai_types.RealtimeInputConfig(
                    automatic_activity_detection=genai_types.AutomaticActivityDetection(
                        end_of_speech_sensitivity="END_SENSITIVITY_HIGH",
                        start_of_speech_sensitivity="START_SENSITIVITY_HIGH",
                        prefix_padding_ms=100,
                        silence_duration_ms=300,
                    )
                ),
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
                "Always speak in English by default. "
                "If the user explicitly speaks in another language (e.g. Bahasa Indonesia), "
                "you may switch to match them, but always start and default to English."
            ),
            llm=llm,
        )
        logger.info(
            "TuntunAgent initialized — instructions set, LLM wired (English default)"
        )

    async def on_enter(self) -> None:
        """Called when agent enters the room and is ready to interact."""
        logger.info("TuntunAgent.on_enter — agent joined the room")
        logger.info("  Generating greeting reply (English)...")

        try:
            t0 = time.monotonic()
            await self.session.generate_reply(
                instructions=(
                    "Greet the user briefly in English and tell them you are "
                    "watching for obstacles. Keep it to one short sentence."
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


# ─── Session Event Loggers ──────────────────────────────────────────────────


def _attach_session_event_loggers(session: AgentSession) -> None:
    """Attach verbose event listeners to an AgentSession so every user/agent
    state transition, speech creation, transcription, and metrics report is
    logged. This makes latency breakdowns (time-to-first-token, duration,
    token counts) visible per turn."""
    logger.info("Attaching session event loggers")

    @session.on("user_state_changed")
    def on_user_state_changed(ev):
        logger.info(
            "[SESSION-EVENT] user_state_changed — old=%s new=%s",
            ev.old_state,
            ev.new_state,
        )

    @session.on("agent_state_changed")
    def on_agent_state_changed(ev):
        logger.info(
            "[SESSION-EVENT] agent_state_changed — old=%s new=%s",
            ev.old_state,
            ev.new_state,
        )

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev):
        logger.info(
            "[SESSION-EVENT] user_input_transcribed — is_final=%s text=%r lang=%s",
            ev.is_final,
            ev.transcript,
            getattr(ev, "language", None),
        )

    @session.on("speech_created")
    def on_speech_created(ev):
        logger.info("[SESSION-EVENT] speech_created — agent started speaking")

    @session.on("conversation_item_added")
    def on_conversation_item_added(ev):
        role = getattr(ev, "role", "<unknown>")
        text = getattr(ev, "text", "") or getattr(ev, "message", "")
        logger.info(
            "[SESSION-EVENT] conversation_item_added — role=%s text=%r",
            role,
            text,
        )

    @session.on("metrics_collected")
    def on_metrics_collected(ev):
        try:
            reports = getattr(ev, "metrics", None) or []
            for report in reports:
                if isinstance(report, RealtimeModelMetrics):
                    logger.info(
                        "[METRICS] realtime_model — "
                        "ttft=%.3fs duration=%.3fs "
                        "input_tokens=%d output_tokens=%d "
                        "tokens/s=%.1f cancelled=%s",
                        report.ttft,
                        report.duration,
                        report.input_tokens,
                        report.output_tokens,
                        report.tokens_per_second,
                        report.cancelled,
                    )
                else:
                    logger.info(
                        "[METRICS] %s — duration=%.3fs",
                        getattr(report, "type", "unknown"),
                        getattr(report, "duration", 0.0),
                    )
        except Exception as exc:
            logger.error("Failed to log metrics: %s", exc, exc_info=True)

    @session.on("error")
    def on_error(ev):
        logger.error("[SESSION-EVENT] error — %s", ev)


# ─── Server + Session Handler ──────────────────────────────────────────────


def _attach_room_event_loggers(room: Any) -> None:
    """Attach verbose event listeners to a livekit.rtc.Room so every
    participant connect/disconnect, track publish/subscribe/fail, and
    connection state change is logged. This makes it obvious when the
    user's mic/camera media fails to reach the agent."""
    logger.info("Attaching room event loggers to room: %s", room.name)

    @room.on("participant_connected")
    def on_participant_connected(participant):
        logger.info(
            "[ROOM-EVENT] participant_connected — identity=%s sid=%s kind=%s state=%s",
            participant.identity,
            participant.sid,
            participant.kind,
            participant.state,
        )

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        logger.info(
            "[ROOM-EVENT] participant_disconnected — identity=%s sid=%s",
            participant.identity,
            participant.sid,
        )

    @room.on("track_published")
    def on_track_published(publication, participant):
        logger.info(
            "[ROOM-EVENT] track_published — participant=%s source=%s kind=%s sid=%s muted=%s",
            participant.identity,
            _track_source_name(publication.source),
            _track_kind_name(publication.kind),
            publication.sid,
            publication.muted,
        )

    @room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):
        logger.info(
            "[ROOM-EVENT] track_subscribed — participant=%s source=%s kind=%s sid=%s trackId=%s",
            participant.identity,
            _track_source_name(publication.source),
            _track_kind_name(publication.kind),
            publication.sid,
            getattr(track, "sid", "<unknown>"),
        )

    @room.on("track_unsubscribed")
    def on_track_unsubscribed(track, publication, participant):
        logger.info(
            "[ROOM-EVENT] track_unsubscribed — participant=%s source=%s sid=%s",
            participant.identity,
            _track_source_name(publication.source),
            publication.sid,
        )

    @room.on("track_subscription_failed")
    def on_track_subscription_failed(sid, participant):
        logger.error(
            "[ROOM-EVENT] track_subscription_failed — trackSid=%s participant=%s",
            sid,
            participant.identity,
        )

    @room.on("track_muted")
    def on_track_muted(publication, participant):
        logger.info(
            "[ROOM-EVENT] track_muted — participant=%s source=%s sid=%s",
            participant.identity,
            _track_source_name(publication.source),
            publication.sid,
        )

    @room.on("track_unmuted")
    def on_track_unmuted(publication, participant):
        logger.info(
            "[ROOM-EVENT] track_unmuted — participant=%s source=%s sid=%s",
            participant.identity,
            _track_source_name(publication.source),
            publication.sid,
        )

    @room.on("connection_state_changed")
    def on_connection_state_changed(connection_state):
        logger.info(
            "[ROOM-EVENT] connection_state_changed — state=%s", connection_state
        )

    @room.on("disconnected")
    def on_disconnected(reason=None):
        logger.info(
            "[ROOM-EVENT] disconnected — reason=%s (%s)",
            reason,
            getattr(reason, "name", "<unknown>"),
        )


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
        _attach_room_event_loggers(ctx.room)
    except Exception as exc:
        logger.error("Failed to attach room event loggers: %s", exc, exc_info=True)

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
        _attach_session_event_loggers(session)
    except Exception as exc:
        logger.error("Failed to attach session event loggers: %s", exc, exc_info=True)

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
