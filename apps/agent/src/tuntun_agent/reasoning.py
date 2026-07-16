"""Reasoning Layer — LangChain + DeepAgents for multi-step detour reasoning.

The Reflex Layer (Gemini Live) is fast and conversational but not a thinker.
For the one case that genuinely needs multi-step reasoning — "find a safer
route that avoids known crowdsourced hazards near me" — we spin up a small
DeepAgents agent (LangChain tool-calling graph) with a single tool that
queries the Convex crowdsourced hazard map. The agent reasons over the
hazard list + the destination and produces a landmark-grounded detour, which
is spoken back via ``generate_reply``.

This is the design doc's "cortex": invoked only on demand via a function_tool,
allowed to be slow (a few seconds), never on the safety-critical hot path.

deepagents.create_deep_agent returns a langgraph CompiledStateGraph; we invoke
it async and pull the final AIMessage text out of the output messages.
"""

from __future__ import annotations

import json
import os
from typing import Any

from deepagents import create_deep_agent
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from livekit.agents import AgentSession

from tuntun_agent.convex import get_convex_client
from tuntun_agent.logging_setup import get_logger

logger = get_logger()

_REASONING_MODEL = "gemini-2.5-flash"
# Default scan radius around the user's current position (meters).
_NEARBY_RADIUS_M = 150

_DETOUR_SYSTEM_PROMPT = (
    "You are the Deep Navigator reasoning layer for a blind pedestrian walking "
    "in Indonesia. You have one tool: query_nearby_hazards, which returns "
    "crowdsourced damaged road/sidewalk hazards near a lat/lng. Given the "
    "user's current position and destination, call the tool to find hazards "
    "near them, then produce a SHORT (2-3 sentences) landmark-grounded detour "
    "advisory in English: name which way to go to avoid the reported hazards, "
    "and reassure them if the path is clear. Be concrete and calm. Do not "
    "mention JSON, coordinates, or that you used a tool."
)


@tool
def query_nearby_hazards(
    latitude: float, longitude: float, radius_meters: int = _NEARBY_RADIUS_M
) -> str:
    """Query crowdsourced damaged road/sidewalk hazards near a point.

    Returns a JSON list of hazards within `radius_meters` (default 150m) of the
    given lat/lng, nearest first. Each item has locationDescription,
    description, status, and distanceMeters. Empty list if none reported.
    """
    secret = os.environ.get("CONVEX_SERVICE_SECRET", "")
    if not secret:
        return "[]"
    client = get_convex_client()
    if client is None:
        return "[]"
    try:
        rows = client.query(
            "hazardAgent:listNearby",
            {
                "secret": secret,
                "latitude": latitude,
                "longitude": longitude,
                "radiusMeters": radius_meters,
            },
        )
        return json.dumps(rows)
    except Exception as exc:
        logger.error("reasoning: query_nearby_hazards failed: %s", exc, exc_info=True)
        return "[]"


def _build_agent() -> Any:
    """Build the DeepAgents detour graph. ponytail: one tool, no subagents /
    filesystem / memory middleware — those are deepagents defaults we don't
    need for a single-shot detour advisory."""
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    llm = ChatGoogleGenerativeAI(model=_REASONING_MODEL, api_key=api_key)
    return create_deep_agent(
        model=llm,
        tools=[query_nearby_hazards],
        system_prompt=_DETOUR_SYSTEM_PROMPT,
    )


def _final_text(result: Any) -> str:
    """Extract the final assistant text from the DeepAgents graph output."""
    messages = result.get("messages", []) if isinstance(result, dict) else []
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        # Some providers return content as a list of parts.
        if isinstance(content, list):
            text = " ".join(
                str(p.get("text", "")) if isinstance(p, dict) else str(p)
                for p in content
            ).strip()
            if text:
                return text
    return ""


async def compute_detour(
    session: AgentSession, origin: tuple[float, float], destination: str
) -> None:
    """Background task: reason about a hazard-aware detour and speak it.

    Invoked by the ``reroute_around_hazards`` function_tool. Best-effort —
    failures degrade to a spoken apology, never crash the session.
    """
    logger.info(
        "Reasoning: detour start — origin=(%.6f,%.6f) destination=%r",
        origin[0],
        origin[1],
        destination,
    )
    try:
        agent = _build_agent()
        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            f"I'm at latitude {origin[0]}, longitude {origin[1]} "
                            f"and I want to walk to: {destination}. Find any "
                            f"crowdsourced hazards near me and tell me a safer "
                            f"way to go."
                        ),
                    }
                ]
            }
        )
        advisory = _final_text(result) or (
            "I could not work out a detour right now — please proceed carefully."
        )
        logger.info("Reasoning: detour advisory len=%d", len(advisory))
        await session.generate_reply(
            instructions=(
                "You are guiding a blind pedestrian. Speak this detour advisory "
                f"to the user clearly and calmly in English, in your own words: "
                f"{advisory}"
            )
        )
    except Exception as exc:
        logger.error("Reasoning: detour failed: %s", exc, exc_info=True)
        await session.generate_reply(
            instructions=(
                "Tell the user briefly in English that you could not check the "
                "route for known hazards right now, and to proceed carefully. "
                "One short sentence."
            )
        )
