"""Deep Navigator — Google Maps helpers + macro-to-micro guidance.

Fetch the macro route from Google Maps, then let the Reflex Layer (which sees
the live camera) ground each maneuver in visible landmarks. All calls are
best-effort — failures degrade to a spoken message, never crash the session.
Requires GOOGLE_MAPS_API_KEY env var.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx
from livekit.agents import AgentSession

from tuntun_agent.logging_setup import get_logger

logger = get_logger()

_MAPS_BASE = "https://maps.googleapis.com/maps/api"
_MAX_ROUTE_STEPS = 5
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Hold strong references to fire-and-forget background tasks so they are not
# garbage-collected mid-run (ruff RUF006). Tasks self-remove on completion.
_background_tasks: set[asyncio.Task[Any]] = set()


def spawn_background_task(coro: Any) -> asyncio.Task[Any]:
    """Schedule a fire-and-forget task and keep a strong ref to it."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


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


async def fetch_route_and_reply(
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
