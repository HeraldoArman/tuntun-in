"""Live Crowdsourced Mapping — silent road-hazard reporting.

When the Reflex agent sees damaged road/sidewalk on the chest camera (a
pothole, broken pavement, open manhole, excavation, blocked sidewalk) that is
NOT immediate danger to the user, it silently reports it to the public
dashboard — no prompt, no spoken confirmation. The flow:

  1. Snapshot the latest buffered camera frame -> JPEG (livekit image encode).
  2. Generate a Convex upload URL -> POST the JPEG -> { storageId }.
  3. Insert a hazardReports row (GPS + description + image id) via the
     hazardAgent:ingestReport mutation.

Every step degrades gracefully: missing GPS, no frame, no Convex secret, or an
upload failure never crash the session — they just log and skip. Silent by
design: no generate_reply, the user is never interrupted.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from livekit.agents import AgentSession
from livekit.agents.utils.images import EncodeOptions, ResizeOptions, encode

from tuntun_agent.convex import get_convex_client
from tuntun_agent.logging_setup import get_logger

logger = get_logger()

_UPLOAD_TIMEOUT = 20.0
# Cap snapshot dimensions so uploads stay small + fast. Aspect-fit so the image
# is not distorted.
_SNAPSHOT_WIDTH = 1024
_SNAPSHOT_HEIGHT = 1024


def _encode_jpeg(frame: Any) -> bytes | None:
    """Encode a rtc.VideoFrame to JPEG bytes, or None on failure."""
    try:
        return encode(
            frame,
            EncodeOptions(
                format="JPEG",
                resize_options=ResizeOptions(
                    width=_SNAPSHOT_WIDTH,
                    height=_SNAPSHOT_HEIGHT,
                    strategy="scale_aspect_fit",
                ),
            ),
        )
    except Exception as exc:
        logger.error("Crowdsource: JPEG encode failed: %s", exc, exc_info=True)
        return None


async def _upload_image(client: Any, jpeg_bytes: bytes) -> str | None:
    """Generate a Convex upload URL, POST the JPEG, return the storageId.

    Returns None on any failure or missing secret. The ConvexClient mutation
    call is synchronous and blocks the loop briefly; acceptable for a one-shot
    background report. The HTTP POST is async via httpx.AsyncClient.
    """
    secret = os.environ.get("CONVEX_SERVICE_SECRET", "")
    if not secret:
        logger.warning(
            "Crowdsource: CONVEX_SERVICE_SECRET not set — cannot upload image"
        )
        return None

    try:
        upload_url = client.mutation(
            "hazardAgent:generateUploadUrl", {"secret": secret}
        )
    except Exception as exc:
        logger.error("Crowdsource: generateUploadUrl failed: %s", exc, exc_info=True)
        return None

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_UPLOAD_TIMEOUT) as http:
            resp = await http.post(
                upload_url,
                content=jpeg_bytes,
                headers={"Content-Type": "image/jpeg"},
            )
            resp.raise_for_status()
            data = resp.json()
        storage_id = data.get("storageId")
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Crowdsource: image uploaded — storageId=%s elapsed=%.1fms",
            storage_id,
            elapsed_ms,
        )
        return str(storage_id) if storage_id else None
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.error(
            "Crowdsource: image POST failed — elapsed=%.1fms error=%s",
            elapsed_ms,
            exc,
            exc_info=True,
        )
        return None


def _create_report(
    client: Any,
    profile_id: str,
    lat: float,
    lng: float,
    location_description: str,
    description: str,
    image_storage_id: str | None,
) -> str | None:
    """Insert a hazardReports row via hazardAgent:ingestReport. Returns the
    report id or None on failure."""
    secret = os.environ.get("CONVEX_SERVICE_SECRET", "")
    if not secret:
        return None
    args: dict[str, Any] = {
        "secret": secret,
        "reporterProfileId": profile_id,
        "latitude": lat,
        "longitude": lng,
        "locationDescription": location_description,
        "description": description,
    }
    if image_storage_id:
        args["imageStorageId"] = image_storage_id
    try:
        report_id = client.mutation("hazardAgent:ingestReport", args)
        logger.info("Crowdsource: report stored — id=%s", report_id)
        return str(report_id) if report_id else None
    except Exception as exc:
        logger.error("Crowdsource: ingestReport failed: %s", exc, exc_info=True)
        return None


async def report_hazard_flow(
    session: AgentSession,
    description: str,
    location_description: str,
) -> None:
    """Background task: snapshot the camera, upload it, and insert a silent
    crowdsourced hazard report. Never speaks to the user. Best-effort."""
    t0 = time.monotonic()
    logger.info(
        "Crowdsource flow start — description=%r location=%r",
        description,
        location_description,
    )

    userdata = session.userdata
    if not isinstance(userdata, dict):
        logger.error("Crowdsource: userdata is not a dict — aborting")
        return

    profile_id = userdata.get("profileId")
    lat = userdata.get("lat")
    lng = userdata.get("lng")
    frame = userdata.get("latest_frame")

    if not profile_id:
        logger.warning("Crowdsource: no profileId in userdata — skipping report")
        return
    if lat is None or lng is None:
        logger.warning(
            "Crowdsource: no GPS fix yet — skipping report (description=%r)",
            description,
        )
        return

    client = get_convex_client()
    if not client:
        logger.warning("Crowdsource: no Convex client — skipping report")
        return

    image_storage_id: str | None = None
    if frame is not None:
        jpeg = _encode_jpeg(frame)
        if jpeg:
            image_storage_id = await _upload_image(client, jpeg)
    else:
        logger.info("Crowdsource: no frame buffered yet — storing report without image")

    report_id = _create_report(
        client,
        str(profile_id),
        float(lat),
        float(lng),
        location_description,
        description,
        image_storage_id,
    )

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info(
        "Crowdsource flow done — elapsed=%.1fms reportId=%s image=%s",
        elapsed_ms,
        report_id,
        "yes" if image_storage_id else "no",
    )
