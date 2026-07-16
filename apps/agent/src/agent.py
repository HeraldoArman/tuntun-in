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

import asyncio
import json
import logging
import os
import re
import sys
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()

import httpx  # noqa: E402
from google.genai import types as genai_types  # noqa: E402
from livekit.agents import (  # noqa: E402
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    cli,
    function_tool,
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


# ─── Deep Navigator — Google Maps helpers ───────────────────────────────────
# Macro-to-micro navigation: fetch the macro route from Google Maps, then let
# the Reflex Layer (which sees the live camera) ground each maneuver in visible
# landmarks. All calls are best-effort — failures degrade to a spoken message,
# never crash the session. Requires GOOGLE_MAPS_API_KEY env var.

_MAPS_BASE = "https://maps.googleapis.com/maps/api"
_MAX_ROUTE_STEPS = 5
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Hold strong references to fire-and-forget background tasks so they are not
# garbage-collected mid-run (ruff RUF006). Tasks self-remove on completion.
_background_tasks: set[asyncio.Task[Any]] = set()


def _strip_html(text: str) -> str:
    """Strip HTML tags from a Maps instruction and collapse whitespace."""
    return _HTML_TAG_RE.sub("", text).replace("&nbsp;", " ").strip()


async def _geocode(api_key: str, address: str) -> tuple[float, float] | None:
    """Geocode a free-text address to (lat, lng). Returns None on failure."""
    url = f"{_MAPS_BASE}/geocode/json"
    params = {"address": address, "key": api_key}
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        elapsed_ms = (time.monotonic() - t0) * 1000
        results = data.get("results") or []
        if not results:
            logger.warning(
                "Geocode returned no results: address=%r elapsed=%.1fms status=%s",
                address,
                elapsed_ms,
                data.get("status"),
            )
            return None
        loc = results[0]["geometry"]["location"]
        lat, lng = float(loc["lat"]), float(loc["lng"])
        logger.info(
            "Geocode success: address=%r -> (%.6f, %.6f) elapsed=%.1fms",
            address,
            lat,
            lng,
            elapsed_ms,
        )
        return lat, lng
    except Exception as exc:
        logger.error("Geocode failed: address=%r error=%s", address, exc, exc_info=True)
        return None


async def _directions(
    api_key: str, origin: tuple[float, float], destination: tuple[float, float]
) -> list[dict[str, Any]] | None:
    """Fetch walking directions and return a compact list of step dicts.

    Each step: {instruction, distance, maneuver}. Returns None on failure.
    """
    url = f"{_MAPS_BASE}/directions/json"
    params = {
        "origin": f"{origin[0]},{origin[1]}",
        "destination": f"{destination[0]},{destination[1]}",
        "mode": "walking",
        "key": api_key,
    }
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        elapsed_ms = (time.monotonic() - t0) * 1000
        routes = data.get("routes") or []
        if not routes:
            logger.warning(
                "Directions returned no routes: elapsed=%.1fms status=%s",
                elapsed_ms,
                data.get("status"),
            )
            return None
        steps_out: list[dict[str, Any]] = []
        for leg in routes[0].get("legs", []):
            for step in leg.get("steps", []):
                steps_out.append(
                    {
                        "instruction": _strip_html(step.get("html_instructions", "")),
                        "distance": (step.get("distance") or {}).get("text", ""),
                        "maneuver": step.get("maneuver", ""),
                    }
                )
                if len(steps_out) >= _MAX_ROUTE_STEPS:
                    break
            if len(steps_out) >= _MAX_ROUTE_STEPS:
                break
        logger.info(
            "Directions success: %d steps (capped at %d) elapsed=%.1fms",
            len(steps_out),
            _MAX_ROUTE_STEPS,
            elapsed_ms,
        )
        return steps_out
    except Exception as exc:
        logger.error("Directions failed: error=%s", exc, exc_info=True)
        return None


async def _fetch_route_and_reply(
    session: AgentSession,
    api_key: str,
    origin: tuple[float, float],
    destination: str,
) -> None:
    """Background task: geocode destination, fetch directions, push a
    landmark-grounded guidance reply via generate_reply. Mirrors the design-doc
    async-tool pattern (return fast, speak result later) to avoid dead-air."""
    t0 = time.monotonic()
    logger.info("Deep Navigator fetch start: destination=%r", destination)

    dest_coords = await _geocode(api_key, destination)
    if dest_coords is None:
        await session.generate_reply(
            instructions=(
                f"Tell the user briefly in English that you could not find a "
                f"place called '{destination}' on the map, and ask them to "
                f"repeat or rephrase it. One short sentence."
            )
        )
        return

    steps = await _directions(api_key, origin, dest_coords)
    if not steps:
        await session.generate_reply(
            instructions=(
                f"Tell the user briefly in English that you could not compute "
                f"a walking route to '{destination}' right now. One short "
                f"sentence, calm tone."
            )
        )
        return

    first = steps[0]
    remaining = len(steps) - 1
    route_summary = (
        f"First maneuver: {first['instruction']} "
        f"(about {first['distance']}). "
        f"{remaining} more step(s) after that."
    )
    steps_block = "\n".join(f"- {s['instruction']} ({s['distance']})" for s in steps)

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info(
        "Deep Navigator route ready: elapsed=%.1fms first=%r",
        elapsed_ms,
        first["instruction"],
    )

    await session.generate_reply(
        instructions=(
            "You are guiding a visually impaired user and you can see their "
            "live chest-mounted camera feed. A walking route was just fetched. "
            f"Route to '{destination}':\n{steps_block}\n\n"
            "Translate the FIRST maneuver into tangible, landmark-based "
            "guidance: anchor the turn/direction to something visible in the "
            "camera right now (a food cart, pole, sign, building color, "
            "parked vehicle, doorway). Only fall back to the metric distance "
            "if no usable landmark is visible. Keep it to one short, clear "
            f"sentence in English. Example style: "
            "'Turn left just past the blue food cart ahead.'\n\n"
            f"Route summary for your reference: {route_summary}"
        )
    )


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
                "You are Tuntun, the Reflex Layer of a mobility companion for visually impaired users. "
                "You are watching a live video feed from a chest-mounted smartphone camera and listening "
                "to the user's microphone. Your PRIMARY job is real-time vision-to-audio obstacle detection.\n\n"
                "RESPONSIVENESS: React instantly (sub-second). Every warning is time-critical — a delayed "
                "warning is a useless warning. Do not over-explain; act first.\n\n"
                "WHAT TO DETECT (Indonesian street context): parked motorcycles on sidewalks, open "
                "manholes, uncovered drainage gutters, potholes, low-hanging banners/awnings, "
                "construction barriers, excavation pits, hanging wires, steps/drops, uneven pavement, "
                "street vendors' carts, and any obstacle in the user's direct path.\n\n"
                "WARNING STYLE: Short, spatial, and urgent. State WHERE (left / center / right / ahead), "
                "WHAT (name the obstacle), and distance if estimable. Examples: "
                "'Watch out, motorcycle ahead center.' 'Step down, drop on your left.' "
                "'Open manhole, two meters ahead, center.'\n\n"
                "PROACTIVE: You MUST warn about danger whenever you see it — you do NOT need to be called "
                "or greeted first. Safety overrides everything.\n\n"
                "LANGUAGE: Always speak in English by default. If the user explicitly speaks in another "
                "language (e.g. Bahasa Indonesia), you may switch to match them for that reply, but "
                "always start and default to English.\n\n"
                "CALM TONE: Be clear and reassuring, never panic-inducing. The user trusts your voice."
                "\n\n"
                "DEEP NAVIGATOR: When the user asks to be guided or navigate to a place (e.g. "
                "'take me to the station', 'guide me to the nearest market'), call the "
                "navigate_to tool with the destination. The tool returns immediately with a "
                "holding message — speak that right away so there is no silence. The actual "
                "route arrives as a follow-up. Once you have a route, ground EACH maneuver in "
                "what the camera shows right now (food carts, signs, poles, building colors, "
                "parked vehicles, doorways) before stating the abstract metric distance — "
                "turn 'turn left in 50 meters' into 'turn left just past the blue food cart'. "
                "Advance to the next maneuver as the user approaches landmarks. Safety "
                "warnings ALWAYS override navigation chatter."
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

    @function_tool()
    async def navigate_to(self, destination: str) -> str:
        """Called when the user asks to be guided or navigated to a place.
        Fetches a walking route from Google Maps and pushes landmark-based
        guidance as a follow-up reply. Returns a short holding message
        immediately so the user does not hear silence while the route is
        being fetched.

        Args:
            destination: The place the user wants to go, as free text
                (e.g. "the train station", "nearest market", "Jl. Sudirman 10").
        """
        api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
        if not api_key:
            logger.warning(
                "navigate_to: GOOGLE_MAPS_API_KEY not set — cannot fetch routes"
            )
            return (
                "I can't fetch maps right now — navigation is not configured. "
                "Please tell the owner to set a Google Maps API key."
            )

        userdata = self.session.userdata
        lat = userdata.get("lat") if isinstance(userdata, dict) else None
        lng = userdata.get("lng") if isinstance(userdata, dict) else None
        if lat is None or lng is None:
            logger.info("navigate_to: no GPS origin yet — destination=%r", destination)
            return (
                "I need your location to route you. Please allow location "
                "access in the browser so I can guide you."
            )

        origin = (float(lat), float(lng))
        logger.info(
            "navigate_to: dispatching background route fetch — destination=%r "
            "origin=(%.6f, %.6f)",
            destination,
            origin[0],
            origin[1],
        )
        # Return fast with a holding message; speak the real route once fetched.
        task = asyncio.create_task(
            _fetch_route_and_reply(self.session, api_key, origin, destination)
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
        logger.info(
            "navigate_to: background task created id=%s destination=%r",
            id(task),
            destination,
        )
        return f"On it — looking up the route to {destination}, give me a moment."


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


def _attach_gps_handler(room: Any, session: AgentSession) -> None:
    """Listen for GPS data packets from the web client and store the latest
    fix on session.userdata. Packets are JSON: {"type":"gps","lat":..,"lng":..}
    on topic "gps". Failures are logged and ignored — GPS is best-effort."""
    logger.info("Attaching GPS data handler to room: %s", room.name)

    @room.on("data_received")
    def on_data_received(data_packet):
        try:
            topic = getattr(data_packet, "topic", None)
            payload = data_packet.data
            if isinstance(payload, (bytes, bytearray)):
                payload_str = payload.decode("utf-8", errors="replace")
            else:
                payload_str = str(payload)
            if topic != "gps":
                return
            parsed = json.loads(payload_str)
            if parsed.get("type") != "gps":
                return
            lat = parsed.get("lat")
            lng = parsed.get("lng")
            if lat is None or lng is None:
                logger.warning("GPS packet missing lat/lng: %r", parsed)
                return
            userdata = session.userdata
            if isinstance(userdata, dict):
                userdata["lat"] = float(lat)
                userdata["lng"] = float(lng)
            logger.info("[GPS] fix stored: lat=%.6f lng=%.6f", float(lat), float(lng))
        except Exception as exc:
            logger.error("Failed to handle GPS data packet: %s", exc, exc_info=True)


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
        _attach_session_event_loggers(session)
    except Exception as exc:
        logger.error("Failed to attach session event loggers: %s", exc, exc_info=True)

    # ── Deep Navigator: receive GPS fixes from the web client ──
    # The web client publishes {type:"gps", lat, lng} on data topic "gps".
    # We store the latest fix on session.userdata so the navigate_to tool can
    # use it as the route origin.
    try:
        _attach_gps_handler(ctx.room, session)
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
