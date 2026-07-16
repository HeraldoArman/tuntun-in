"""Overwatch Mode — emergency spectator + WhatsApp alert.

When the Reflex agent detects critical danger (a fall, entering an excavation
area, an imminent collision), it triggers Overwatch:

  1. Mint a one-shot spectator LiveKit token for the current room (subscribe
     to the blind user's camera + publish audio so the guardian can guide them
     verbally).
  2. Build a secret spectator URL and register an Overwatch session in Convex
     (resolving the blind user's linked guardian).
  3. Send the spectator URL to the guardian's WhatsApp number via GoWA
     (go-whatsapp-web-multidevice REST API). Best-effort.
  4. Push a spoken follow-up so the blind user knows help is connecting.

All steps degrade gracefully: missing env, no guardian, or a GoWA failure never
crash the session — they just change what the agent says next.
"""

from __future__ import annotations

import datetime
import os
import time
import urllib.parse
from typing import Any

import httpx
from livekit import api as livekit_api
from livekit.agents import AgentSession

from tuntun_agent.convex import get_convex_client
from tuntun_agent.logging_setup import get_logger

logger = get_logger()

_SPECTATOR_TOKEN_TTL = datetime.timedelta(hours=1)
_WHATSAPP_TIMEOUT = 15.0


def _normalize_phone(phone: str) -> str:
    """Normalize a WhatsApp number/JID to GoWA send format: digits only.

    Strips spaces, dashes, and any '@s.whatsapp.net' suffix. GoWA accepts a
    bare country-code number (e.g. '6281234567890').
    """
    cleaned = phone.strip().replace(" ", "").replace("-", "")
    if "@" in cleaned:
        cleaned = cleaned.split("@", 1)[0]
    return cleaned


def mint_spectator_token(room_name: str) -> str | None:
    """Mint a LiveKit token for a guardian to join `room_name` as a spectator.

    Grants: join the room, subscribe (see the blind user's camera + hear audio),
    publish (audio only — to guide the user verbally). Visible (not hidden) so
    the blind user can see their guardian connected. Returns the JWT or None
    if LiveKit credentials are not configured.
    """
    api_key = os.environ.get("LIVEKIT_API_KEY", "")
    api_secret = os.environ.get("LIVEKIT_API_SECRET", "")
    if not api_key or not api_secret:
        logger.warning("Overwatch: LIVEKIT_API_KEY/SECRET not set — no spectator token")
        return None

    identity = f"guardian-{room_name}-{int(time.time())}"
    try:
        token = (
            livekit_api.AccessToken(api_key, api_secret)
            .with_identity(identity)
            .with_grants(
                livekit_api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=False,
                    hidden=False,
                )
            )
            .with_ttl(_SPECTATOR_TOKEN_TTL)
        )
        jwt = token.to_jwt()
        logger.info(
            "Overwatch: spectator token minted — identity=%s room=%s ttl=%s",
            identity,
            room_name,
            _SPECTATOR_TOKEN_TTL,
        )
        return jwt
    except Exception as exc:
        logger.error(
            "Overwatch: failed to mint spectator token: %s", exc, exc_info=True
        )
        return None


def build_spectator_url(token: str, room_name: str) -> str | None:
    """Build the public spectator URL the guardian opens from WhatsApp.

    Carries the LiveKit token + server URL as query params so the spectator
    page can join without any further server round-trip. Requires PUBLIC_WEB_URL
    + LIVEKIT_URL env. Returns None if PUBLIC_WEB_URL is not set.
    """
    base = os.environ.get("PUBLIC_WEB_URL", "").rstrip("/")
    if not base:
        logger.warning("Overwatch: PUBLIC_WEB_URL not set — cannot build spectator URL")
        return None
    server = os.environ.get("LIVEKIT_URL", "")
    params = urllib.parse.urlencode(
        {"token": token, "room": room_name, "server": server}
    )
    url = f"{base}/spectator?{params}"
    logger.info("Overwatch: spectator URL built — room=%s len=%d", room_name, len(url))
    return url


async def send_whatsapp(phone: str, message: str) -> bool:
    """Send a WhatsApp text message via GoWA. Best-effort — returns True on
    success, False on any failure or missing config. Never raises."""
    base_url = os.environ.get("GOWA_BASE_URL", "").rstrip("/")
    device_id = os.environ.get("GOWA_DEVICE_ID", "")
    if not base_url or not device_id:
        logger.warning(
            "Overwatch: GoWA not configured (GOWA_BASE_URL/GOWA_DEVICE_ID) — "
            "skipping WhatsApp send"
        )
        return False

    phone_clean = _normalize_phone(phone)
    url = f"{base_url}/send/message"
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Device-Id": device_id,
    }
    # Optional basic auth if the GoWA instance is secured.
    username = os.environ.get("GOWA_USERNAME", "")
    password = os.environ.get("GOWA_PASSWORD", "")
    if username and password:
        import base64

        creds = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"

    payload = {"phone": phone_clean, "message": message}
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_WHATSAPP_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Overwatch: WhatsApp sent — to=%s code=%s elapsed=%.1fms",
            phone_clean,
            data.get("code"),
            elapsed_ms,
        )
        return True
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.error(
            "Overwatch: WhatsApp send failed — to=%s elapsed=%.1fms error=%s",
            phone_clean,
            elapsed_ms,
            exc,
            exc_info=True,
        )
        return False


def _create_session(
    profile_id: str, room_name: str, spectator_url: str, reason: str
) -> dict[str, Any] | None:
    """Call the Convex overwatchAgent.startForAgent mutation. Returns the
    guardian info dict or None on failure. Synchronous (ConvexClient is sync)
    — called from a background task, blocks the loop briefly. # ponytail: sync
    convex call in async task; acceptable for a one-shot trigger."""
    secret = os.environ.get("CONVEX_SERVICE_SECRET", "")
    if not secret:
        logger.warning(
            "Overwatch: CONVEX_SERVICE_SECRET not set — skipping session record"
        )
        return None

    client = get_convex_client()
    if not client:
        logger.warning("Overwatch: no Convex client — skipping session record")
        return None

    try:
        result = client.mutation(
            "overwatchAgent:startForAgent",
            {
                "secret": secret,
                "blindUserProfileId": profile_id,
                "livekitRoomName": room_name,
                "spectatorUrl": spectator_url,
                "reason": reason,
            },
        )
        logger.info(
            "Overwatch: session created — sessionId=%s guardian=%s whatsapp=%s",
            result.get("sessionId"),
            result.get("guardianFullName"),
            "yes" if result.get("guardianWhatsappNumber") else "no",
        )
        return result
    except Exception as exc:
        logger.error("Overwatch: startForAgent failed: %s", exc, exc_info=True)
        return None


def _mark_whatsapp_sent(session_id: str, sent: bool) -> None:
    """Record the WhatsApp delivery result on the session. Best-effort."""
    secret = os.environ.get("CONVEX_SERVICE_SECRET", "")
    if not secret:
        return
    client = get_convex_client()
    if not client:
        return
    try:
        client.mutation(
            "overwatchAgent:markWhatsappSent",
            {"secret": secret, "sessionId": session_id, "sent": sent},
        )
        logger.info("Overwatch: marked whatsappSent=%s on %s", sent, session_id)
    except Exception as exc:
        logger.error("Overwatch: markWhatsappSent failed: %s", exc, exc_info=True)


async def trigger_overwatch_flow(session: AgentSession, reason: str) -> None:
    """Background task: mint spectator token, register the Overwatch session,
    send the WhatsApp alert, then speak a follow-up to the blind user.

    Reads profileId + roomName from session.userdata (published by the web
    client / set at entrypoint). Every step is best-effort — the spoken
    follow-up adapts to what actually succeeded.
    """
    t0 = time.monotonic()
    logger.info("Overwatch flow start — reason=%r", reason)

    userdata = session.userdata
    if not isinstance(userdata, dict):
        logger.error("Overwatch: userdata is not a dict — aborting")
        return

    room_name = userdata.get("roomName")
    profile_id = userdata.get("profileId")
    if not room_name:
        logger.error("Overwatch: no roomName in userdata — aborting")
        await session.generate_reply(
            instructions=(
                "Tell the user briefly in English that you tried to alert their "
                "guardian but could not identify the session. One short sentence."
            )
        )
        return
    if not profile_id:
        logger.error("Overwatch: no profileId in userdata — aborting")
        await session.generate_reply(
            instructions=(
                "Tell the user briefly in English that you want to alert their "
                "guardian but cannot identify their account, and ask them to "
                "make sure they are logged in. One short sentence."
            )
        )
        return

    token = mint_spectator_token(room_name)
    spectator_url = build_spectator_url(token, room_name) if token else None
    if not spectator_url:
        logger.error("Overwatch: could not build spectator URL — aborting WhatsApp")
        await session.generate_reply(
            instructions=(
                "Tell the user briefly in English that you detected a critical "
                "danger and want to alert their guardian, but the live-view link "
                "is not configured. One short, calm sentence."
            )
        )
        return

    session_info = _create_session(profile_id, room_name, spectator_url, reason)
    guardian_name = (session_info or {}).get("guardianFullName")
    guardian_number = (session_info or {}).get("guardianWhatsappNumber")
    session_id = (session_info or {}).get("sessionId")

    whatsapp_sent = False
    if guardian_number:
        message = (
            f"🚨 Tuntun.In Overwatch alert — {guardian_name or 'your linked user'} "
            f"may be in danger ({reason}). View their live camera and guide them "
            f"here: {spectator_url}"
        )
        whatsapp_sent = await send_whatsapp(guardian_number, message)
        if session_id:
            _mark_whatsapp_sent(str(session_id), whatsapp_sent)

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info(
        "Overwatch flow done — elapsed=%.1fms guardian=%s whatsappSent=%s",
        elapsed_ms,
        "yes" if guardian_number else "no",
        whatsapp_sent,
    )

    # Speak a calm, situation-aware follow-up. The immediate danger warning was
    # already issued by the agent before calling the tool — this is the
    # "help is connecting" reassurance.
    if guardian_number and whatsapp_sent:
        await session.generate_reply(
            instructions=(
                f"You just detected critical danger: {reason}. Tell the user "
                f"briefly and calmly in English that you have alerted their "
                f"guardian {guardian_name or ''} by WhatsApp and that their "
                f"guardian can now see their camera and guide them. Reassure "
                f"them. One or two short sentences."
            )
        )
    elif guardian_number and not whatsapp_sent:
        await session.generate_reply(
            instructions=(
                f"You just detected critical danger: {reason}. Tell the user "
                f"briefly in English that you tried to alert their guardian "
                f"{guardian_name or ''} but the message could not be sent right "
                f"now. Stay calm and keep moving carefully. One short sentence."
            )
        )
    else:
        await session.generate_reply(
            instructions=(
                f"You just detected critical danger: {reason}. Tell the user "
                f"briefly in English that you triggered an Overwatch alert but "
                f"no guardian is linked to their account yet, so they should "
                f"add a family member as a guardian in the app settings. One "
                f"short, calm sentence."
            )
        )
