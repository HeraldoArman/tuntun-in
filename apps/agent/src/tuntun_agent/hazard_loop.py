"""Hazard Detection Loop — the second, independent trigger source.

A separate perception loop that subscribes to the chest-camera feed (via the
``latest_frame`` buffered on ``session.userdata`` by ``events.attach_video_frame_capture``)
and classifies hazards with a fast non-realtime Gemini model. Each detected
hazard is fed to the ``PriorityManager`` which owns the cooldown + interrupt
policy.

Why a separate loop (not just Gemini Live's own vision)?
  The Reflex Layer (Gemini Live) is conversational and gated behind the wake
  word; its turn coverage is not a reliable always-on detector. This loop gives
  us full control over sampling rate, classification, cooldown, and the 3-level
  priority classification — exactly as the design doc prescribes.

Cost ceiling: one gemini-2.5-flash image call every ``_SAMPLE_INTERVAL`` seconds
(~40/min at 1.5s). ponytail: fine for a demo; raise the interval or switch to a
cheaper vision model if billing matters.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from google import genai
from google.genai import types
from livekit.agents import AgentSession
from livekit.agents.utils.images import EncodeOptions, ResizeOptions, encode

from tuntun_agent.logging_setup import get_logger
from tuntun_agent.priority import Hazard, HazardPriority, PriorityManager

logger = get_logger()

# Sampling interval. Lower = faster warnings, higher Gemini cost.
_SAMPLE_INTERVAL = 1.5
# Fast non-realtime vision model for per-frame classification. gemini-2.5-flash
# is gated ("no longer available to new users") on newer API keys; 3.1-flash-lite
# is GA, cheap, and good enough for hazard classification. Override via env.
_HAZARD_MODEL = os.environ.get("HAZARD_MODEL", "gemini-3.1-flash-lite")
# Downscale frames before classification — keeps latency + cost low.
_CLASSIFY_WIDTH = 640
_CLASSIFY_HEIGHT = 640

_PRIORITY_MAP = {
    "critical": HazardPriority.CRITICAL,
    "moderate": HazardPriority.MODERATE,
    "low": HazardPriority.LOW,
}

# JSON schema returned by the classifier.
_HAZARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hazards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": [
                            "step_down",
                            "pothole",
                            "open_manhole",
                            "drainage_gutter",
                            "excavation_pit",
                            "vehicle",
                            "motorcycle_parked",
                            "construction_barrier",
                            "low_obstruction",
                            "uneven_pavement",
                            "other",
                        ],
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["critical", "moderate", "low"],
                    },
                },
                "required": ["description", "kind", "priority"],
            },
        }
    },
    "required": ["hazards"],
}

_CLASSIFY_PROMPT = (
    "You are a street-hazard detector for a blind user wearing a chest-mounted "
    "camera walking in Indonesia. Look at this ONE frame and detect ONLY hazards "
    "that are unambiguously visible AND in the user's direct walking path within "
    "about 3 meters. Classify each one:\n"
    "- critical: imminent life-threatening danger — a fall, an excavation pit / "
    "deep hole about to be stepped into, an oncoming vehicle on collision course.\n"
    "- moderate: obstacle in the path needing action now — open manhole, pothole, "
    "steps/drop, drainage gutter, blocked sidewalk, construction barrier.\n"
    "- low: minor additional info — uneven pavement, low-hanging banner/awning, "
    "hanging wires, a parked motorcycle on the sidewalk.\n"
    "Return JSON {hazards:[{description,kind,priority}]}. `kind` is a stable "
    "category from the enum — use it so the same physical hazard is deduped "
    "across frames. `description` is a short spatial note (e.g. 'open manhole "
    "2m ahead center', 'motorcycle on left').\n"
    "ANTI-HALLUCINATION RULES (critical — a false warning is dangerous):\n"
    "- Only report a hazard you can point to in this frame. Do NOT infer a "
    "hazard from shadows, wet patches, discoloration, blurriness, or texture.\n"
    "- A shadow or a dark patch on the ground is NOT a pothole. A seam between "
    "paving slabs is NOT a step down. A change in surface color is NOT a drop.\n"
    "- If the same flat, continuous walking surface extends ahead with no "
    "obvious vertical drop or obstacle, that is a CLEAR path — return an empty "
    "array. Do not invent 'uneven pavement' or 'step down' on a normal sidewalk.\n"
    "RETURN AN EMPTY hazards ARRAY when any of these hold — do not invent a "
    "hazard to fill the silence:\n"
    "- the image is dark, black, underexposed, or the camera appears covered;\n"
    "- the image is blurry, smeared, or too low-quality to identify ground "
    "features;\n"
    "- no street, sidewalk, path, or ground is visible (e.g. indoor, a wall, "
    "sky only, a person's face or body filling the frame with no walking path);\n"
    "- the path ahead is clear and unobstructed.\n"
    "When in ANY doubt, return an empty array. Silence is safer than a false "
    "warning for a blind walker."
)


class HazardLoop:
    """Periodically classify the latest camera frame and feed the Priority
    Manager. Best-effort — any failure logs and the next tick retries."""

    def __init__(self, session: AgentSession, pm: PriorityManager) -> None:
        self._session = session
        self._pm = pm
        self._task: asyncio.Task[Any] | None = None
        self._stopped = False

        api_key = os.environ.get("GOOGLE_API_KEY", "")
        self._client = genai.Client(api_key=api_key) if api_key else None
        if self._client is None:
            logger.warning(
                "HazardLoop: GOOGLE_API_KEY not set — proactive hazard "
                "detection disabled (wake word still works)"
            )
        else:
            logger.info(
                "HazardLoop ready — model=%s interval=%.1fs",
                _HAZARD_MODEL,
                _SAMPLE_INTERVAL,
            )

    def start(self) -> None:
        if self._client is None:
            return
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        logger.info("HazardLoop running")
        try:
            while not self._stopped:
                await asyncio.sleep(_SAMPLE_INTERVAL)
                if self._stopped:
                    break
                await self._tick()
        except asyncio.CancelledError:
            logger.info("HazardLoop cancelled")
        except Exception as exc:
            logger.error("HazardLoop fatal: %s", exc, exc_info=True)

    async def _tick(self) -> None:
        userdata = self._session.userdata
        if not isinstance(userdata, dict):
            return
        frame = userdata.get("latest_frame")
        if frame is None or self._client is None:
            return

        try:
            jpeg = encode(
                frame,
                EncodeOptions(
                    format="JPEG",
                    quality=70,
                    resize_options=ResizeOptions(
                        width=_CLASSIFY_WIDTH,
                        height=_CLASSIFY_HEIGHT,
                        strategy="scale_aspect_fit",
                    ),
                ),
            )
        except Exception as exc:
            logger.error("HazardLoop: frame encode failed: %s", exc, exc_info=True)
            return

        try:
            resp = await self._client.aio.models.generate_content(
                model=_HAZARD_MODEL,
                contents=[
                    types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                    types.Part.from_text(text=_CLASSIFY_PROMPT),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_HAZARD_SCHEMA,
                    temperature=0.2,
                ),
            )
        except Exception as exc:
            logger.error("HazardLoop: classify failed: %s", exc, exc_info=True)
            return

        hazards = self._parse(resp)
        # Process highest-priority hazards first so a CRITICAL warning is never
        # queued behind a MODERATE/LOW one returned in the same frame. This
        # complements the non-blocking MODERATE deferral in the PriorityManager
        # (which prevents a CRITICAL in a *later* tick from being stalled).
        priority_rank = {
            HazardPriority.CRITICAL: 0,
            HazardPriority.MODERATE: 1,
            HazardPriority.LOW: 2,
        }
        for h in sorted(hazards, key=lambda x: priority_rank.get(x.priority, 99)):
            await self._pm.on_hazard(h)

    @staticmethod
    def _parse(resp: Any) -> list[Hazard]:
        text = getattr(resp, "text", None) or ""
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("HazardLoop: non-JSON response: %s — %r", exc, text[:200])
            return []
        out: list[Hazard] = []
        for item in data.get("hazards", []) or []:
            desc = str(item.get("description", "")).strip()
            if not desc:
                continue
            priority = _PRIORITY_MAP.get(
                str(item.get("priority", "")).lower(), HazardPriority.LOW
            )
            kind = str(item.get("kind", "")).strip().lower() or "other"
            out.append(Hazard(description=desc, priority=priority, kind=kind))
        return out

    async def stop(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.info("HazardLoop stopped")


def attach_hazard_loop(session: AgentSession, pm: PriorityManager) -> HazardLoop:
    """Create and start a HazardLoop feeding the given PriorityManager."""
    loop = HazardLoop(session, pm)
    loop.start()
    return loop
