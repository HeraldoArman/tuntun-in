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
      MODERATE  -> if SPEAKING, defer (non-blocking) and speak once the
                   current speech ends, unless a CRITICAL preempts it
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

# Seconds before the same hazard (by kind) may warn again. Dedup is by stable
# `kind`, not the free-text description, so a rephrased detection of the same
# physical hazard does not re-fire every few seconds.
_COOLDOWN = 8.0


class HazardPriority(Enum):
    CRITICAL = "critical"
    MODERATE = "moderate"
    LOW = "low"


@dataclass
class Hazard:
    """A detected road/street hazard fed into the Priority Manager."""

    description: str
    priority: HazardPriority
    # Stable category (e.g. "pothole", "step_down") from the classifier. Used as
    # the cooldown key so the same physical hazard is not re-announced every
    # frame just because the free-text description changed wording.
    kind: str = "other"


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


def _hazard_instructions(hazard: Hazard, urgent: bool) -> str:
    """Build the generate_reply instruction for a spoken hazard warning.

    The agent has the live chest-camera feed, so it must VERIFY the classifier's
    claim against the frame before speaking — a cheap vision model can
    hallucinate a pothole that isn't there. It must also avoid fabricated
    steering ("keep to the center") that could guide the user into something it
    didn't check, and vary its wording so warnings don't sound templated.
    """
    tone = "urgent and sharp" if urgent else "calm and matter-of-fact"
    return (
        f"A hazard detector reported: {hazard.description} (category: {hazard.kind}). "
        f"Before speaking, LOOK at your live camera frame right now and VERIFY this "
        f"is actually visible in the user's path.\n"
        f"- If you CANNOT clearly see it in the frame, DO NOT announce a specific "
        f"obstacle. Say nothing, or at most a brief, vague 'careful with your step' "
        f"without naming anything. A false warning is dangerous.\n"
        f"- If it IS visible: state WHAT it is and WHERE (left / center / right / "
        f"ahead) in one short sentence. Give a distance only if you can actually "
        f"estimate it from the frame.\n"
        f"- DO NOT invent steering like 'keep to the center' or 'move left' unless "
        f"you can clearly see, in the frame right now, that the suggested side is "
        f"actually free of obstacles. If you can't confirm a safe direction, just "
        f"name the obstacle and its location — let the user choose.\n"
        f"- Vary your wording. Do not repeat the same templated phrase (e.g. "
        f"'{hazard.description}') verbatim — rephrase naturally each time.\n"
        f"Tone: {tone}. English. One short sentence."
    )


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
        # Set when NOT speaking, cleared when speaking. lets a deferred
        # MODERATE hazard wait for the end of the current speech before firing.
        self._not_speaking = asyncio.Event()
        self._not_speaking.set()
        # Deferred MODERATE state: when a MODERATE hazard arrives while the
        # agent is speaking, we must NOT block the perception loop on
        # wait_for_speech_end (that would stall the hazard loop and delay a
        # later CRITICAL). Instead we stage it here and let a background
        # waiter fire it once speech ends — unless a CRITICAL preempts it.
        self._pending_moderate: Hazard | None = None
        self._deferred_task: asyncio.Task[None] | None = None
        # monotonic timestamp of the last CRITICAL warning actually spoken, so
        # a deferred MODERATE can tell if a CRITICAL fired while it was waiting
        # and drop itself instead of clobbering the life-threatening warning.
        self._last_critical_monotonic: float = 0.0
        # Set when the room disconnects. Once true, on_hazard / _speak / _interrupt
        # no-op so the hazard loop's deferred tasks stop firing generate_reply on
        # a dead session (the "AgentSession isn't running" storm that starves the
        # user's real turns with cancelled zero-duration replies).
        self._stopped: bool = False

    @property
    def design_state(self) -> str:
        return _design_state(self._livekit_state)

    def stop(self) -> None:
        """Stop accepting hazards + cancel any deferred MODERATE waiter.

        Called on room disconnect so background deferred tasks don't keep
        calling generate_reply on a session that is no longer running.
        """
        self._stopped = True
        self._cancel_deferred()

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
        """Apply the cooldown + 3-level interrupt policy for one hazard.

        Non-blocking: a MODERATE hazard that arrives while the agent is
        speaking is deferred (not awaited) so the perception loop keeps
        sampling and a later CRITICAL can preempt immediately. The deferred
        MODERATE is cancelled if a CRITICAL arrives while it is waiting, so a
        non-critical warning can never clobber a life-threatening one.
        """
        key = hazard.kind or hazard.description
        now = time.monotonic()
        if self._stopped:
            return
        if now - self._last_warned.get(key, 0.0) < _COOLDOWN:
            logger.debug(
                "[PRIORITY] skip (cooldown) — kind=%r priority=%s",
                key,
                hazard.priority.value,
            )
            return

        state = self.design_state
        logger.info(
            "[PRIORITY] hazard — priority=%s state=%s kind=%r desc=%r",
            hazard.priority.value,
            state,
            key,
            hazard.description,
        )

        if hazard.priority is HazardPriority.CRITICAL:
            # Safety overrides everything — cut whatever is being said and
            # cancel any deferred MODERATE so it cannot fire after us.
            self._cancel_deferred()
            self._last_critical_monotonic = time.monotonic()
            await self._interrupt()
            await self._speak(_hazard_instructions(hazard, urgent=True))
        elif hazard.priority is HazardPriority.MODERATE:
            if state == STATE_SPEAKING:
                # Do NOT block the perception loop on wait_for_speech_end —
                # that would stall the hazard loop and delay a later CRITICAL.
                # Defer: the latest MODERATE fires once speech ends, unless a
                # CRITICAL preempts it first.
                self._defer_moderate(hazard)
                return
            await self._interrupt()
            await self._speak(_hazard_instructions(hazard, urgent=False))
        else:  # LOW
            if state == STATE_IDLE:
                await self._speak(_hazard_instructions(hazard, urgent=False))
            else:
                logger.debug("[PRIORITY] skip LOW (agent busy) — kind=%r", key)
                # Not spoken: do NOT stamp cooldown, so it can fire once idle.
                return

        self._last_warned[key] = time.monotonic()

    def _defer_moderate(self, hazard: Hazard) -> None:
        """Stage a MODERATE hazard to fire once the current speech ends.

        Only one deferred waiter exists at a time; a newer MODERATE replaces an
        older pending one (no queue buildup). The waiter runs as a background
        task so it never blocks the caller (the hazard loop tick).
        """
        self._pending_moderate = hazard
        if self._deferred_task is None or self._deferred_task.done():
            self._deferred_task = asyncio.create_task(self._deferred_moderate_speak())

    def _cancel_deferred(self) -> None:
        """Cancel any pending deferred MODERATE (e.g. because a CRITICAL fired)."""
        self._pending_moderate = None
        task = self._deferred_task
        if task is not None and not task.done():
            task.cancel()
        self._deferred_task = None

    async def _deferred_moderate_speak(self) -> None:
        """Background waiter: speak the latest deferred MODERATE once the
        current speech ends, unless a CRITICAL preempted it while waiting."""
        started = time.monotonic()
        try:
            await self._not_speaking.wait()
        except asyncio.CancelledError:
            return
        hazard = self._pending_moderate
        self._pending_moderate = None
        self._deferred_task = None
        if hazard is None:
            return  # cancelled by a CRITICAL
        # A CRITICAL fired while we were waiting — never clobber it.
        if self._last_critical_monotonic > started:
            logger.debug(
                "[PRIORITY] drop deferred MODERATE (CRITICAL preempted) — %r",
                hazard.description,
            )
            return
        # Re-check cooldown: another warning for the same kind may have fired
        # while we were waiting.
        key = hazard.kind or hazard.description
        if time.monotonic() - self._last_warned.get(key, 0.0) < _COOLDOWN:
            return
        await self._interrupt()
        await self._speak(_hazard_instructions(hazard, urgent=False))
        self._last_warned[key] = time.monotonic()

    async def _interrupt(self) -> None:
        if self._stopped:
            return
        try:
            await self._session.interrupt()
        except Exception as exc:
            logger.warning("[PRIORITY] interrupt failed: %s", exc)

    async def _speak(self, instructions: str) -> None:
        if self._stopped:
            return
        try:
            await self._session.generate_reply(instructions=instructions)
        except Exception as exc:
            logger.error("[PRIORITY] generate_reply failed: %s", exc, exc_info=True)


def attach_priority_manager(session: AgentSession) -> PriorityManager:
    """Create a PriorityManager for the session and wire its state tracker.

    Returns the manager so the caller can feed it hazards (e.g. from the
    hazard detection loop).
    """
    pm = PriorityManager(session)
    pm.attach(session)
    logger.info("PriorityManager attached — cooldown=%.1fs", _COOLDOWN)
    return pm
