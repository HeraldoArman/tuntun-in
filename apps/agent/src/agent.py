"""
Tuntun.In AI Mobility Companion Agent — entrypoint.

Dual-brain architecture:
- Reflex Layer: Gemini Live (instant audio-visual obstacle detection +
  spatial warnings). Gated behind the "Hey Tutu" wake word for reactive
  conversation.
- Hazard Detection Loop: separate perception loop (fast Gemini flash per
  frame) feeding a Priority Manager that owns the state machine + 3-level
  interrupt policy + per-hazard cooldown. Proactive warnings bypass the wake
  gate.
- Reasoning Layer: LangChain + DeepAgents, invoked on demand via the
  reroute_around_hazards function_tool to reason about a hazard-aware detour.
- Deep Navigator: Google Maps directions via the navigate_to function_tool,
  grounded in live camera landmarks.

Wake word gating: the agent is gated behind the "Hey Tutu" wake word
(openwakeword ONNX model). Until the wake word is detected, the agent stays
silent and does not react to ambient speech — so it won't interrupt when the
user is talking to someone else. Proactive hazard warnings come from the
separate hazard loop, not the wake word path.

The implementation lives in the `tuntun_agent` package. This file wires up
logging, the AgentServer, and the per-room session handler. Logging is verbose
by design — configure level via LOG_LEVEL env var (default: INFO).

# ponytail: thin entrypoint only. All behavior is in tuntun_agent.* modules.
load_dotenv() runs before importing tuntun_agent so LOG_LEVEL is read from env.
"""

from __future__ import annotations

import time

from dotenv import load_dotenv

# override=True so a stale/empty shell export can't shadow the .env values
# (e.g. an exported GOOGLE_MAPS_API_KEY="" in a parent shell would otherwise
# leave the Deep Navigator without a Maps key even though .env defines it).
load_dotenv(
    override=True
)  # must run before tuntun_agent imports (LOG_LEVEL read at import)

from livekit.agents import (  # noqa: E402
    AgentServer,
    AgentSession,
    JobContext,
    cli,
    room_io,
)

from tuntun_agent.agent import TuntunAgent  # noqa: E402
from tuntun_agent.convex import aping_convex, get_convex_client  # noqa: E402
from tuntun_agent.events import (  # noqa: E402
    attach_data_handlers,
    attach_room_event_loggers,
    attach_session_event_loggers,
    attach_video_frame_capture,
)
from tuntun_agent.hazard_loop import attach_hazard_loop  # noqa: E402
from tuntun_agent.logging_setup import (  # noqa: E402
    get_logger,
    log_startup_env,
    setup_logging,
)
from tuntun_agent.navigator import spawn_background_task  # noqa: E402
from tuntun_agent.priority import attach_priority_manager  # noqa: E402
from tuntun_agent.wakeword import attach_wake_word  # noqa: E402

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
        # Use the async ping so the (blocking) ConvexClient mutation runs in a
        # worker thread and never stalls the event loop — important because the
        # agent's audio pipeline shares this loop.
        await aping_convex(client, label="session_start")
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
                # MANUAL turn detection: the agent does NOT auto-react to
                # every sound. Turns are opened explicitly by the wake word
                # detector ("Hey Tutu") or by the proactive safety loop. This
                # prevents the agent from interrupting when the user is
                # talking to someone else.
                "turn_detection": "manual",
                "endpointing": {
                    "mode": "fixed",
                    "min_delay": 0.2,
                    "max_delay": 0.8,
                },
                "preemptive_generation": {
                    "enabled": True,
                    "preemptive_tts": True,
                },
            },
            # Deep Navigator origin: latest GPS fix published by the web client
            # via the LiveKit data channel (topic "gps"). Updated by the
            # data_received handler below; read by the navigate_to tool.
            # profileId: blind user's Convex profile id (topic "profile"), read
            # by the Overwatch tool to resolve the linked guardian.
            # roomName: set here so the Overwatch tool can mint a spectator
            # token for this room without inspecting room_io internals.
            userdata={
                "lat": None,
                "lng": None,
                "profileId": None,
                "roomName": ctx.room.name,
                # Latest chest-camera VideoFrame + its rtc.VideoStream, kept by
                # attach_video_frame_capture. Read by the report_road_hazard
                # (Crowdsourced Mapping) tool to snapshot + upload a JPEG.
                "latest_frame": None,
                "video_stream": None,
            },
        )
        logger.info(
            "AgentSession created: elapsed=%.1fms "
            "(turn_detection=manual, aec_warmup=0.5s, "
            "endpointing min=0.2s max=0.8s, preemptive=on)",
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

    # ── Priority Manager (state machine + hazard/conversation arbiter) ──
    # Owns the IDLE / ACTIVE_CONVERSATION / SPEAKING state (driven by
    # agent_state_changed) and the 3-level CRITICAL/MODERATE/LOW interrupt
    # policy + per-hazard cooldown. Fed by the hazard detection loop below.
    try:
        priority_manager = attach_priority_manager(session)
    except Exception as exc:
        logger.error("Failed to attach PriorityManager: %s", exc, exc_info=True)
        priority_manager = None

    # ── Deep Navigator + Overwatch: receive data from the web client ──
    # The web client publishes on two data topics:
    #   "gps"      -> {type:"gps", lat, lng}          (Deep Navigator origin)
    #   "profile"  -> {type:"profile", profileId}     (blind user Convex id,
    #                used by the Overwatch tool to resolve the guardian)
    # roomName is set here (known from ctx) so the Overwatch tool can mint a
    # spectator token for this exact room without reaching into room_io.
    try:
        attach_data_handlers(ctx.room, session)
    except Exception as exc:
        logger.error("Failed to attach data handlers: %s", exc, exc_info=True)

    # ── Crowdsourced Mapping: buffer the latest camera frame ──
    # The report_road_hazard tool snapshots session.userdata["latest_frame"]
    # (a rtc.VideoFrame) and uploads it as JPEG. Best-effort.
    try:
        attach_video_frame_capture(ctx.room, session)
    except Exception as exc:
        logger.error("Failed to attach video frame capture: %s", exc, exc_info=True)

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

    # ── Wake word gating ("Hey Tutu") ──
    # With manual turn detection above, the agent stays silent until the wake
    # word is detected. attach_wake_word subscribes to the user's mic, runs the
    # openwakeword ONNX model, and opens a listening turn on detection. A
    # proactive safety loop also opens periodic turns so Gemini can still emit
    # urgent obstacle warnings. Best-effort — failure logs but never crashes.
    try:
        attach_wake_word(session, ctx.room)
        logger.info("Wake word detector attached — gating active ('Hey Tutu')")
    except Exception as exc:
        logger.error("Failed to attach wake word detector: %s", exc, exc_info=True)

    # ── Hazard Detection Loop (proactive warnings, bypasses wake word) ──
    # The second independent trigger source. Samples the chest-camera frame
    # every ~1.5s, classifies hazards with a fast Gemini model, and feeds them
    # to the PriorityManager which decides interrupt/skip/cooldown. This
    # replaces the wakeword module's old proactive poll and gives full control
    # over priority + cooldown, as the design doc prescribes.
    if priority_manager is not None:
        try:
            hazard_loop = attach_hazard_loop(session, priority_manager)
            logger.info("Hazard detection loop attached — proactive warnings on")

            # Stop the hazard loop + priority manager when the room disconnects
            # so they don't keep firing generate_reply on a dead session (the
            # "AgentSession isn't running" storm that starves the user's real
            # turns with cancelled zero-duration replies).
            @ctx.room.on("disconnected")
            def _on_room_disconnected(reason=None):
                logger.info(
                    "[ROOM-EVENT] stopping hazard loop + priority manager "
                    "on disconnect — reason=%s",
                    reason,
                )
                priority_manager.stop()
                spawn_background_task(hazard_loop.stop())
        except Exception as exc:
            logger.error("Failed to attach hazard loop: %s", exc, exc_info=True)

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
