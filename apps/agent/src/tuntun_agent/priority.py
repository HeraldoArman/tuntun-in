"""Priority Manager + agent state machine.

The Reflex Layer has two independent trigger sources that converge on one
output audio channel:

  1. Wake word ("Hey Tutu")   -> reactive conversation (opens a user turn).
  2. Hazard detection loop    -> proactive warnings (bypasses the wake gate).

Both call ``session.generate_reply``. Without an arbiter, a casual chat can
queue ahead of an urgent hazard, two replies collide, or a fresh danger is
spoken only after the previous sentence finishes — too late for an emergency.

The ``PriorityManager`` is that arbiter. It owns:

  * the agent state machine (IDLE / ACTIVE_CONVERSATION / SPEAKING), driven by
    LiveKit's ``agent_state_changed`` events,
  * a per-hazard cooldown (``_COOLDOWN`` seconds) so the same hazard is not
    repeated but different hazards can still stack,
  * the 3-level interrupt policy from the design doc:

      CRITICAL  -> interrupt() + generate_reply SEGERA (always preempts)
      MODERATE  -> if SPEAKING, wait for the current speech to end, then
                   interrupt the user turn + generate_reply
      LOW       -> only speak if IDLE; otherwise skip (not time-critical)

There is no native ``wait_for_speech_end`` on AgentSession, so we track the
speaking -> non-speaking transition ourselves with an ``asyncio.Event`` that is
cleared on entering "speaking" and set on leaving it.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from livekit.agents import AgentSession

from tuntun_agent.logging_setup import get_logger

logger = get_logger()

# Seconds before the same hazard (by description key) may warn again.
_COOLDOWN = 5.0


class HazardPriority(Enum):
    CRITICAL = "critical"
    MODERATE = "moderate"
    LOW = "low"


@dataclass
class Hazard:
    """A detected road/street hazard fed into the Priority Manager."""

    description: str
    priority: HazardPriority


# Design-doc states, derived from LiveKit's AgentState
# (initializing / idle / listening / thinking / speaking).
STATE_IDLE = "IDLE"
STATE_ACTIVE_CONVERSATION = "ACTIVE_CONVERSATION"
STATE_SPEAKING = "SPEAKING"


def _design_state(livekit_state: str) -> str:
    """Map a LiveKit AgentState to the design-doc state machine state."""
    if livekit_state == "speaking":
        return STATE_SPEAKING
    if livekit_state in ("listening", "thinking"):
        return STATE_ACTIVE_CONVERSATION
    return STATE_IDLE  # initializing / idle


class PriorityManager:
    """Arbiter between proactive hazard warnings and reactive conversation.

    Instantiate after the AgentSession is created, then call ``attach(session)``
    to wire the ``agent_state_changed`` listener, and feed detected hazards via
    ``on_hazard``. Thread-safe by virtue of the single asyncio event loop.
    """

    def __init__(self, session: AgentSession) -> None:
        self._session = session
        self._last_warned: dict[str, float] = {}
        self._livekit_state = "idle"
        # Set when NOT speaking, cleared when speaking. lets a MODERATE hazard
        # await the end of the current speech before interrupting.
        self._not_speaking = asyncio.Event()
        self._not_speaking.set()

    @property
    def design_state(self) -> str:
        return _design_state(self._livekit_state)

    def attach(self, session: AgentSession) -> None:
        """Track agent state transitions so on_hazard knows when it is safe to
        interrupt, and so MODERATE hazards can wait for speech to end."""

        @session.on("agent_state_changed")
        def _on_state_changed(ev: Any) -> None:
            old = self._livekit_state
            new = ev.new_state
            self._livekit_state = new
            if new == "speaking":
                self._not_speaking.clear()
            elif old == "speaking":
                self._not_speaking.set()
            logger.debug(
                "[PRIORITY] state %s -> %s (design=%s)",
                old,
                new,
                self.design_state,
            )

    async def wait_for_speech_end(self) -> None:
        """Block until the agent is no longer speaking (or already isn't)."""
        await self._not_speaking.wait()

    async def on_hazard(self, hazard: Hazard) -> None:
        """Apply the cooldown + 3-level interrupt policy for one hazard."""
        key = hazard.description
        now = time.monotonic()
        if now - self._last_warned.get(key, 0.0) < _COOLDOWN:
            logger.debug(
                "[PRIORITY] skip (cooldown) — %r priority=%s", key, hazard.priority.value
            )
            return

        state = self.design_state
        logger.info(
            "[PRIORITY] hazard — priority=%s state=%s desc=%r",
            hazard.priority.value,
            state,
            key,
        )

        if hazard.priority is HazardPriority.CRITICAL:
            # Safety overrides everything — cut whatever is being said.
            await self._interrupt()
            await self._speak(f"PERINGATAN SEGERA: {hazard.description}")
        elif hazard.priority is HazardPriority.MODERATE:
            if state == STATE_SPEAKING:
                await self.wait_for_speech_end()
            await self._interrupt()
            await self._speak(f"Peringatan: {hazard.description}")
        else:  # LOW
            if state == STATE_IDLE:
                await self._speak(hazard.description)
            else:
                logger.debug(
                    "[PRIORITY] skip LOW (agent busy) — %r", key
                )
                # Not spoken: do NOT stamp cooldown, so it can fire once idle.
                return

        self._last_warned[key] = time.monotonic()

    async def _interrupt(self) -> None:
        try:
            await self._session.interrupt()
        except Exception as exc:
            logger.warning("[PRIORITY] interrupt failed: %s", exc)

    async def _speak(self, instructions: str) -> None:
        try:
            await self._session.generate_reply(instructions=instructions)
        except Exception as exc:
            logger.error(
                "[PRIORITY] generate_reply failed: %s", exc, exc_info=True
            )


def attach_priority_manager(session: AgentSession) -> PriorityManager:
    """Create a PriorityManager for the session and wire its state tracker.

    Returns the manager so the caller can feed it hazards (e.g. from the
    hazard detection loop).
    """
    pm = PriorityManager(session)
    pm.attach(session)
    logger.info("PriorityManager attached — cooldown=%.1fs", _COOLDOWN)
    return pm
