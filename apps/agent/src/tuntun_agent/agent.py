"""TuntunAgent — the Reflex Layer.

Uses Gemini Live for instant multimodal responses: live camera frames + user
audio → spatial audio warnings. Also exposes the navigate_to function_tool
that the Deep Navigator uses to fetch a macro route and push landmark-grounded
guidance.
"""

from __future__ import annotations

import os
import time

from google.genai import types as genai_types
from livekit.agents import Agent, function_tool
from livekit.plugins import google

from tuntun_agent.logging_setup import get_logger
from tuntun_agent.navigator import fetch_route_and_reply, spawn_background_task

logger = get_logger()

TUNTUN_INSTRUCTIONS = (
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
)


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

        super().__init__(instructions=TUNTUN_INSTRUCTIONS, llm=llm)
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
        task = spawn_background_task(
            fetch_route_and_reply(self.session, api_key, origin, destination)
        )
        logger.info(
            "navigate_to: background task created id=%s destination=%r",
            id(task),
            destination,
        )
        return f"On it — looking up the route to {destination}, give me a moment."
