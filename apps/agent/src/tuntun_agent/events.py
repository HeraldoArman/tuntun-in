"""Verbose LiveKit event loggers + GPS data handler.

Every participant connect/disconnect, track publish/subscribe/fail, connection
state change, user/agent state transition, speech creation, transcription, and
per-turn metrics report is logged so latency breakdowns and media failures are
visible during development and production.
"""

from __future__ import annotations

import json
from typing import Any

from livekit.agents import AgentSession
from livekit.agents.metrics import RealtimeModelMetrics

from tuntun_agent.logging_setup import get_logger

logger = get_logger()

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


def attach_session_event_loggers(session: AgentSession) -> None:
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


def attach_gps_handler(room: Any, session: AgentSession) -> None:
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


def attach_room_event_loggers(room: Any) -> None:
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
