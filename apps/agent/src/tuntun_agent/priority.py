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
# Max seconds a background follow-up waits for the agent to finish speaking
# before firing its own generate_reply. Bounds the wait so a wedged speaking
# state can never hang the follow-up (and the user) forever; after the cap it
# proceeds best-effort. Generous: a spoken turn reply is ~3-5s.
_WAIT_SPEECH_END_TIMEOUT = 12.0


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

    Kept text-only + fast: the spoken reply must be quick so it does not hold
    the per-session reply lock and starve a background navigator/reasoning
    follow-up (which would re-introduce the 60s silence). Hallucination is
    handled at the classifier layer (it has the frame and runs cheaply per
    tick), not here. The only rules here are cheap text rules: no fabricated
    steering, and rephrase so warnings don't sound templated.
    """
    tone = "urgent and sharp" if urgent else "calm and matter-of-fact"
    return (
        f"A hazard was detected in the user's path: {hazard.description} "
        f"(category: {hazard.kind}). Warn the user in ONE short English "
        f"sentence: state WHAT it is and WHERE (left / center / right / ahead), "
        f"and a distance only if one was given in the description.\n"
        f"- Do NOT invent steering like 'keep to the center' or 'move left' — "
        f"you cannot see a safe side from this text alone. Just name the "
        f"obstacle and its location; let the user choose which way to go.\n"
        f"- Rephrase naturally. Do NOT repeat the description verbatim.\n"
        f"Tone: {tone}. English. One short sentence."
    )


async def speak_serialized(session: AgentSession, instructions: str) -> None:
    """Speak a background follow-up via generate_reply without racing the
    agent's current turn reply, the hazard loop, or another follow-up on the
    same Gemini Live session.

    Two guards:
    1. Wait for the agent to stop speaking (not_speaking_event) BEFORE firing,
       so the follow-up does not collide with the in-flight turn reply (which
       LiveKit speaks itself and does not take the lock). Capped at
       _WAIT_SPEECH_END_TIMEOUT so a stuck-speaking state can never hang the
       follow-up forever — after the cap it proceeds best-effort.
    2. Acquire the per-session reply_lock so two follow-ups (or a follow-up and
       a hazard warning) can't both call generate_reply at once (the loser would
       time out waiting for generation_created -> 60s silence).

    Best-effort: dead-session (RuntimeError), timeout, and cancellation errors
    are logged and swallowed, never raised into the background task.
    """
    userdata = getattr(session, "userdata", None)
    lock = userdata.get("reply_lock") if isinstance(userdata, dict) else None
    # Prefer idle_event (true IDLE = turn reply done) over not_speaking_event
    # (set during `thinking` too — waiting on it races LiveKit's own turn
    # reply). Falls back to not_speaking_event if idle_event isn't published.
    idle_event = userdata.get("idle_event") if isinstance(userdata, dict) else None
    not_speaking = (
        userdata.get("not_speaking_event") if isinstance(userdata, dict) else None
    )
    wait_event = idle_event or not_speaking
    t0 = time.monotonic()
    try:
        # Guard 1: don't fire while the agent is mid-turn (turn reply in flight
        # or speaking). Timeout-bounded so a wedged state can't deadlock.
        if wait_event is not None:
            try:
                await asyncio.wait_for(
                    wait_event.wait(), timeout=_WAIT_SPEECH_END_TIMEOUT
                )
            except TimeoutError:
                logger.warning(
                    "[SERIALIZE-RACE] idle/speech-end wait TIMEOUT %.1fs — "
                    "proceeding best-effort (wedged state?)",
                    time.monotonic() - t0,
                )
        speech_wait = time.monotonic() - t0
        if speech_wait > 0.2:
            logger.info(
                "[SERIALIZE-RACE] waited %.2fs for idle before lock",
                speech_wait,
            )
        if lock is None:
            # No PriorityManager attached — degrade to an unlocked speak.
            await session.generate_reply(instructions=instructions)
            return
        # Guard 2: serialize with any other reply on this session.
        async with lock:
            lock_wait = time.monotonic() - t0
            if lock_wait > 0.2:
                # >0.2s means another reply (hazard/wake/another follow-up) was
                # holding the lock — serialization working as designed, but the
                # follow-up is delayed. Long values starve the user's request.
                logger.info(
                    "[SERIALIZE-RACE] lock acquired after %.2fs (contended)",
                    lock_wait,
                )
            await session.generate_reply(instructions=instructions)
        logger.info(
            "[SERIALIZE-RACE] speak done — total=%.2fs",
            time.monotonic() - t0,
        )
    except (RuntimeError, TimeoutError, asyncio.CancelledError) as exc:
        logger.warning(
            "[SERIALIZE-RACE] generate_reply dropped after %.2fs — %s",
            time.monotonic() - t0,
            exc,
        )
    except Exception as exc:
        logger.error(
            "[SERIALIZE-RACE] generate_reply failed after %.2fs — %s",
            time.monotonic() - t0,
            exc,
            exc_info=True,
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
        # Serializes every generate_reply on this session. Gemini Live runs one
        # generation at a time on a manual-turn session; without a lock, the
        # hazard loop's reply and a background follow-up (navigator route,
        # reasoning detour) race and the loser times out waiting for
        # generation_created -> the user hears silence for 60s. Hazards still
        # preempt via interrupt() (cancels the holder; the lock releases on the
        # raised CancelledError), so CRITICAL safety is never blocked.
        self._reply_lock = asyncio.Lock()
        # Set when NOT speaking, cleared when speaking. lets a deferred
        # MODERATE hazard wait for the end of the current speech before firing.
        self._not_speaking = asyncio.Event()
        self._not_speaking.set()
        # Set when the session is truly IDLE (no user turn in flight, agent not
        # speaking/thinking). A deferred MODERATE waits on THIS, not
        # ``_not_speaking``: ``_not_speaking`` is set during ``thinking`` too
        # (LiveKit generating the user's turn reply), so waiting on it would
        # fire our hazard generate_reply mid-turn and race LiveKit's own turn
        # reply (which does NOT take reply_lock) -> generation_created timeout
        # -> user hears silence and repeats the wake word. Waiting for IDLE
        # guarantees the turn reply is done before we speak.
        self._idle_event = asyncio.Event()
        self._idle_event.set()
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
            # _idle_event tracks the true IDLE design state. Set only when we
            # land in IDLE (initializing/idle); cleared the moment we leave it
            # for ACTIVE_CONVERSATION or SPEAKING. See __init__ for why the
            # deferred MODERATE waits on this instead of _not_speaking.
            new_design = _design_state(new)
            if new_design == STATE_IDLE:
                self._idle_event.set()
            else:
                self._idle_event.clear()
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
            logger.warning(
                "[HAZARD-RACE] CRITICAL preempt — state=%s kind=%r desc=%r "
                "(cancelling holder of reply_lock if any)",
                state,
                key,
                hazard.description,
            )
            self._cancel_deferred()
            self._last_critical_monotonic = time.monotonic()
            await self._interrupt()
            await self._speak(_hazard_instructions(hazard, urgent=True))
        elif hazard.priority is HazardPriority.MODERATE:
            if state != STATE_IDLE:
                # Defer while the user's turn is in flight (ACTIVE_CONVERSATION)
                # OR the agent is speaking. Firing a MODERATE generate_reply
                # here would clobber/race LiveKit's own turn reply (which does
                # NOT take reply_lock) -> generation_created timeout -> the
                # user hears silence and repeats the wake word 5+ times. The
                # deferred waiter holds for IDLE (turn fully done) so we speak
                # right after, not mid-turn. CRITICAL still preempts via
                # interrupt() — only MODERATE/LOW yield to the user's turn.
                logger.info(
                    "[HAZARD-RACE] defer MODERATE — state=%s kind=%r (wait for IDLE)",
                    state,
                    key,
                )
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
        session is truly IDLE (user's turn reply finished), unless a CRITICAL
        preempted it while waiting.

        Waits on ``_idle_event`` (not ``_not_speaking``) so the turn reply
        completes first — see __init__ for why this is what closes the race.
        """
        started = time.monotonic()
        try:
            await self._idle_event.wait()
        except asyncio.CancelledError:
            logger.info(
                "[HAZARD-RACE] deferred MODERATE cancelled (CRITICAL preempted) "
                "after %.2fs",
                time.monotonic() - started,
            )
            return
        wait = time.monotonic() - started
        hazard = self._pending_moderate
        self._pending_moderate = None
        self._deferred_task = None
        if hazard is None:
            logger.info(
                "[HAZARD-RACE] deferred MODERATE nothing left after %.2fs wait",
                wait,
            )
            return  # cancelled by a CRITICAL
        # A CRITICAL fired while we were waiting — never clobber it.
        if self._last_critical_monotonic > started:
            logger.info(
                "[HAZARD-RACE] drop deferred MODERATE (CRITICAL preempted) "
                "after %.2fs — %r",
                wait,
                hazard.description,
            )
            return
        logger.info(
            "[HAZARD-RACE] deferred MODERATE firing after %.2fs wait — %r",
            wait,
            hazard.description,
        )
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
        # Hold the reply lock so the hazard reply can't race a background
        # navigator/reasoning follow-up on the same Gemini Live session.
        t0 = time.monotonic()
        try:
            async with self._reply_lock:
                lock_wait = time.monotonic() - t0
                if lock_wait > 0.2:
                    # Hazard warning blocked behind a wake/navigator/follow-up
                    # reply. CRITICAL should have preempted via interrupt(); a
                    # long wait here for a CRITICAL means the holder wasn't
                    # cancelled and the safety warning was delayed.
                    logger.warning(
                        "[HAZARD-RACE] CRITICAL/MODERATE lock wait=%.2fs — "
                        "safety warning delayed behind another reply",
                        lock_wait,
                    )
                await self._session.generate_reply(instructions=instructions)
        except Exception as exc:
            logger.error(
                "[HAZARD-RACE] generate_reply failed after %.2fs — %s",
                time.monotonic() - t0,
                exc,
                exc_info=True,
            )


def attach_priority_manager(session: AgentSession) -> PriorityManager:
    """Create a PriorityManager for the session and wire its state tracker.

    Returns the manager so the caller can feed it hazards (e.g. from the
    hazard detection loop). Also publishes two coordination primitives on
    session.userdata so background follow-ups (navigator, reasoning) can avoid
    racing the agent's turn reply or each other:

    - "reply_lock": asyncio.Lock serializing every generate_reply on the session
    - "not_speaking_event": asyncio.Event set when the agent is NOT speaking,
      so a follow-up can wait for the current turn reply / hazard warning to
      finish before firing its own generate_reply (closes the turn-vs-followup
      race that the lock alone can't cover, since the turn reply is spoken by
      LiveKit's own machinery and does not take the lock).
    """
    pm = PriorityManager(session)
    pm.attach(session)
    userdata = getattr(session, "userdata", None)
    if isinstance(userdata, dict):
        userdata["reply_lock"] = pm._reply_lock
        userdata["not_speaking_event"] = pm._not_speaking
        userdata["idle_event"] = pm._idle_event
    logger.info("PriorityManager attached — cooldown=%.1fs", _COOLDOWN)
    return pm
