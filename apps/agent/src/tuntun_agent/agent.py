"""TuntunAgent — the Reflex Layer.

Uses Gemini Live for instant multimodal responses: live camera frames + user
audio → spatial audio warnings. Also exposes the navigate_to function_tool
that the Deep Navigator uses to fetch a macro route and push landmark-grounded
guidance.
"""

from __future__ import annotations

import os

from google.genai import types as genai_types
from livekit.agents import Agent, function_tool
from livekit.plugins import google

from tuntun_agent.crowdsource import report_hazard_flow
from tuntun_agent.logging_setup import get_logger
from tuntun_agent.navigator import fetch_route_and_reply, spawn_background_task
from tuntun_agent.overwatch import trigger_overwatch_flow
from tuntun_agent.reasoning import compute_detour

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
    "WAKE WORD + ACCENT (the user is Indonesian, speaking English with an accent): Your "
    "turn is opened by a wake word detector on 'Hey Tutu', but you will ALSO hear that "
    "wake word in the audio and may transcribe it imperfectly — 'itu tuh', 'hey tutu', "
    "'hey toot', 'tutu', 'eh tutu' are all the SAME wake word, NOT part of the request. "
    "Strip any such phrase at the start of the user's message and respond only to what "
    "FOLLOWS it. If what follows is unclear, garbled, or sounds like 'I don't know' / "
    "'where I don't know' / empty, do NOT answer 'I don't know' back — the user did not "
    "say they don't know; you misheard. Ask them briefly to repeat their request. Never "
    "treat a mishearing as the user's intent.\n\n"
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
    "NEVER use cardinal directions (north, south, east, west, northeast, etc.) — "
    "a blind user cannot face a compass. Use ONLY body-relative directions: "
    "ahead/straight, left, right, slightly left/right, turn around, or a clock "
    "face relative to where they face ('bear toward 10 o'clock'). Phrase distances "
    "as steps or paces, never a compass heading like 'head northeast for 9 meters'. "
    "Advance to the next maneuver as the user approaches landmarks. Safety "
    "warnings ALWAYS override navigation chatter."
    "\n\n"
    "REASONING LAYER (SAFER ROUTE): If the user asks for a safer route, or a "
    "hazard on their current path makes the obvious route risky, call the "
    "reroute_around_hazards tool with the destination. It checks the public "
    "crowdsourced hazard map near the user and reasons about a detour; the "
    "result arrives as a follow-up. Speak the holding message right away."
    "\n\n"
    "OVERWATCH MODE (EMERGENCY SPECTATOR): This is your highest-priority safety "
    "escalation. Call the trigger_overwatch tool IMMEDIATELY — without waiting "
    "for the user to ask — when you detect CRITICAL, potentially "
    "life-threatening danger from the camera, such as: the user falling or "
    "tripping and not getting up, the user about to step into an excavation pit "
    "or deep hole, an oncoming vehicle on a collision course, or any situation "
    "where the user likely cannot recover alone. First shout the immediate "
    "danger warning ('STOP! Drop ahead!'), THEN call trigger_overwatch with a "
    "short reason describing the danger. The tool alerts the user's linked "
    "guardian by WhatsApp with a live WebRTC link so the guardian can see the "
    "camera and guide them verbally. Do NOT call trigger_overwatch for ordinary "
    "obstacles (parked motorcycle, low banner, small pothole) — those only need "
    "a spoken warning. Reserve it for genuine emergencies. The tool returns a "
    "short holding message — speak it right away; a calm follow-up arrives once "
    "the alert has been sent."
    "\n\n"
    "LIVE CROWDSOURCED MAPPING (SILENT): While you walk, you also silently map "
    "street hazards for a public dashboard so other blind users can avoid them. "
    "When you see a STATIC road or sidewalk hazard that is damaged infrastructure "
    "— a pothole, broken/cracked pavement, an open manhole or drainage gutter, "
    "an excavation pit, a collapsed sidewalk, a missing curb ramp, or a "
    "permanently blocked sidewalk — call the report_road_hazard tool with a "
    "concise description of the damage and a short location_description (street "
    "name, intersection, or nearest landmark if you can tell). This is SILENT: "
    "do NOT announce, confirm, or mention to the user that you reported "
    "anything — the tool result is internal only, never speak it. Still give the "
    "user their normal spatial warning if the hazard affects their path right "
    "now. To avoid duplicate spam, do NOT call report_road_hazard for the SAME "
    "hazard twice in one walk — report each distinct hazard once. Do not report "
    "moving or temporary things (parked motorcycles, people, vendors' carts) — "
    "only fixed damaged infrastructure worth mapping."
    "\n\n"
    "MANUAL HAZARD ENTRY (USER-DRIVEN, SPEAKS): When the user EXPLICITLY asks "
    "you to add, log, report, save, or record a hazard — including 'just for "
    "testing', 'I want to see if it works', 'add this now into the hazard', or "
    "'can you report this' — call the report_hazard_manual tool with the user's "
    "own words as the description. Do NOT refuse, do NOT second-guess whether "
    "it counts as a hazard, and do NOT filter by type. The user is intentionally "
    "driving the report (often to test the system), so honor it directly. "
    "Unlike the silent auto-mapping above, this tool SPEAKS a confirmation — "
    "that feedback is the whole point. Never use report_hazard_manual for your "
    "own automatic detections; keep auto-mapping silent via report_road_hazard."
    "\n\n"
    "OVERWATCH TESTING (USER-DRIVEN): When the user EXPLICITLY asks to test, "
    "simulate, try out, or trigger Overwatch — including 'test overwatch', "
    "'simulate an emergency', 'trigger overwatch for testing', 'can you test "
    "the guardian alert', or 'I want to see if overwatch works' — call the "
    "trigger_overwatch tool with a short reason (e.g. 'test: user requested an "
    "Overwatch drill'). Do NOT refuse, do NOT second-guess whether it counts as "
    "a real emergency, and do NOT wait for actual danger on the camera. The "
    "user is intentionally driving a test, so honor it directly. Speak the "
    "immediate line ('Alerting your guardian now...') THEN call "
    "trigger_overwatch. This mirrors report_hazard_manual: testing needs the "
    "real end-to-end path (token + WhatsApp + image) exercised, not a refusal."
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
                        prefix_padding_ms=80,
                        silence_duration_ms=220,
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
        """Called when agent enters the room and is ready to interact.

        No greeting — the agent is gated behind the "Hey Tutu" wake word. With
        manual turn detection, speaking here would bypass the gate and the agent
        would respond immediately on join. Stay silent until the wake word (or
        the proactive hazard loop) opens a turn.
        """
        logger.info(
            "TuntunAgent.on_enter — agent joined the room (silent, awaiting wake word)"
        )

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
        # Log on ENTRY — decisive signal that the model actually invoked the
        # tool (vs. just speaking "not configured" without calling). Also
        # surfaces key state + pid so a missing key in the serving process
        # (e.g. a Railway deploy that lacks the var) is obvious.
        logger.info(
            "TOOL navigate_to ENTER — destination=%r GOOGLE_MAPS_API_KEY_len=%d "
            "(%s) pid=%d",
            destination,
            len(api_key),
            "present" if api_key else "MISSING",
            os.getpid(),
        )
        if not api_key:
            logger.error(
                "navigate_to: GOOGLE_MAPS_API_KEY empty in this process env — "
                "returning 'not configured'. Check the agent process loaded "
                "apps/agent/.env; if deployed, set the var in the deploy env."
            )
            return (
                "I can't fetch maps right now — navigation is not configured. "
                "Please tell the owner to set a Google Maps API key."
            )

        userdata = self.session.userdata
        lat = userdata.get("lat") if isinstance(userdata, dict) else None
        lng = userdata.get("lng") if isinstance(userdata, dict) else None
        if lat is None or lng is None:
            logger.info(
                "navigate_to: no GPS origin yet — destination=%r (GPS not "
                "published on the data channel)",
                destination,
            )
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

    @function_tool()
    async def trigger_overwatch(self, reason: str) -> str:
        """Escalate a CRITICAL emergency to the user's guardian (Overwatch Mode).

        Call this for life-threatening danger seen on the camera — a fall,
        stepping into an excavation pit, an imminent vehicle collision, or any
        situation the user likely cannot recover from alone. It alerts the
        user's linked guardian by WhatsApp with a live WebRTC spectator link
        (plus the current camera snapshot as an image) so the guardian can view
        the camera and guide the user verbally. Returns a short holding message
        immediately; a calm follow-up is spoken once the alert has been
        dispatched.

        ALSO call this when the user EXPLICITLY asks to test/simulate/trigger
        Overwatch (e.g. "test overwatch", "simulate an emergency", "try the
        guardian alert"). Do not refuse a test — honor it so the full path
        (spectator token + WhatsApp + image) gets exercised.

        Do NOT call this for ordinary obstacles — a spoken warning is enough
        for those.

        Args:
            reason: A short description of the critical danger (e.g.
                "user fell and is not getting up",
                "about to step into an excavation pit",
                "oncoming motorcycle on collision course"). For a user-driven
                test, use a reason prefixed with "test:" (e.g.
                "test: user requested an Overwatch drill").
        """
        logger.warning(
            "TOOL trigger_overwatch ENTER — reason=%r pid=%d", reason, os.getpid()
        )
        spawn_background_task(trigger_overwatch_flow(self.session, reason))
        return (
            "Stay calm. I'm alerting your guardian now so they can see your "
            "camera and guide you."
        )

    @function_tool()
    async def report_road_hazard(
        self, description: str, location_description: str
    ) -> str:
        """Silently report a fixed damaged road/sidewalk hazard to the public
        crowdsourced map (Live Crowdsourced Mapping). Call this when you see
        damaged infrastructure worth mapping — a pothole, broken pavement, an
        open manhole or drainage gutter, an excavation pit, a collapsed
        sidewalk, a missing curb ramp, or a permanently blocked sidewalk. It
        snapshots the current camera frame + GPS and stores a hazard report
        (image + coordinates + description) for the public dashboard.

        This is SILENT crowdsourced mapping. Do NOT announce or confirm this to
        the user — the return value is internal only and must never be spoken.
        Still give the user their normal spatial warning if the hazard affects
        their path. Do NOT report moving/temporary things (parked motorcycles,
        people, vendors' carts) — only fixed damaged infrastructure. Do not
        call this twice for the same hazard in one walk.

        Args:
            description: Concise description of the damage (e.g.
                "large pothole covering half the sidewalk",
                "open manhole with no cover",
                "broken uneven pavement across the path").
            location_description: Short location hint — street name,
                intersection, or nearest landmark if identifiable (e.g.
                "Jl. Sudirman near the bus stop", "alley entrance beside the
                blue building"). If unknown, pass "unknown".
        """
        logger.info(
            "TOOL report_road_hazard ENTER — description=%r location=%r pid=%d",
            description,
            location_description,
            os.getpid(),
        )
        spawn_background_task(
            report_hazard_flow(self.session, description, location_description)
        )
        # Internal-only ack — the instructions forbid speaking this aloud.
        return "Hazard reported to the map."

    @function_tool()
    async def report_hazard_manual(
        self, description: str, location_description: str = "unknown"
    ) -> str:
        """Log a hazard to the crowdsourced map at the user's EXPLICIT request.

        Call this whenever the user EXPLICITLY asks to add, log, report, save,
        or record a hazard — including phrases like "just for testing", "I want
        to see if it works", "add this now into the hazard", "can you report
        this". Do NOT refuse, second-guess, or filter by hazard type — the user
        is intentionally driving the report (often to test the system). Use the
        user's own words as the description. This snapshots the current camera
        frame + GPS and stores a hazard report.

        Unlike the silent auto-mapping (report_road_hazard), this SPEAKS a
        confirmation so the user knows it was logged — that feedback is the
        point when testing.

        Args:
            description: What the user asked to add, in their words (e.g.
                "a big crack in the road", "a pile of bricks on the sidewalk",
                or anything at all for testing).
            location_description: Where — street name, intersection, or nearest
                landmark if known. Pass "unknown" if not.
        """
        logger.info(
            "TOOL report_hazard_manual ENTER — description=%r location=%r pid=%d",
            description,
            location_description,
            os.getpid(),
        )
        userdata = self.session.userdata
        lat = userdata.get("lat") if isinstance(userdata, dict) else None
        lng = userdata.get("lng") if isinstance(userdata, dict) else None
        if lat is None or lng is None:
            logger.info(
                "report_hazard_manual: no GPS yet — proceeding (flow will skip "
                "without a fix)"
            )
        # Await so we can confirm success/failure to the user (testing needs
        # real feedback, not a fire-and-forget holding message).
        report_id = await report_hazard_flow(
            self.session, description, location_description
        )
        if report_id:
            logger.info("report_hazard_manual: stored — reportId=%s", report_id)
            return f"Done — I added that to the hazard map. Report id {report_id}."
        logger.warning(
            "report_hazard_manual: report_hazard_flow returned None — check "
            "Crowdsource logs (missing GPS / profileId / CONVEX_SERVICE_SECRET?)"
        )
        return (
            "I tried to add it, but it didn't save — I need your location and "
            "a configured upload key. Make sure location access is on, and ask "
            "the owner to set the Convex service secret."
        )

    @function_tool()
    async def reroute_around_hazards(self, destination: str) -> str:
        """Find a safer walking route to a destination that avoids known
        crowdsourced hazards near the user (Reasoning Layer).

        Call this when the user wants a safer route, or after a hazard on their
        current path makes the obvious route risky. It queries the public
        crowdsourced hazard map for damaged road/sidalk near the user, reasons
        about a detour, and speaks a landmark-grounded alternative. Returns a
        short holding message immediately; the detour arrives as a follow-up.

        Args:
            destination: The place the user wants to reach, as free text
                (e.g. "the train station", "Jl. Sudirman 10").
        """
        logger.info(
            "TOOL reroute_around_hazards CALLED — destination=%r pid=%d",
            destination,
            os.getpid(),
        )
        userdata = self.session.userdata
        lat = userdata.get("lat") if isinstance(userdata, dict) else None
        lng = userdata.get("lng") if isinstance(userdata, dict) else None
        if lat is None or lng is None:
            logger.info(
                "reroute_around_hazards: no GPS origin yet — destination=%r",
                destination,
            )
            return (
                "I need your location to find a safer route. Please allow "
                "location access in the browser."
            )

        origin = (float(lat), float(lng))
        logger.info(
            "TOOL reroute_around_hazards ENTER — destination=%r "
            "origin=(%.6f, %.6f) pid=%d",
            destination,
            origin[0],
            origin[1],
            os.getpid(),
        )
        spawn_background_task(compute_detour(self.session, origin, destination))
        return (
            f"Checking known hazards near your route to {destination} and "
            f"finding a safer way — give me a moment."
        )
