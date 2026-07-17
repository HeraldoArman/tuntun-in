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
      MODERATE  -> if no safe gap, defer (non-blocking, bounded) and speak
                   once a safe gap opens, unless a CRITICAL preempts it
      LOW       -> only speak if IDLE; otherwise skip (not time-critical)

"Safe gap" = agent state in {listening, idle, initializing} AND user not
speaking. Firing OUR ``generate_reply`` outside a safe gap collides with
LiveKit's own turn reply (which does not take ``reply_lock``) -> generation
timeout -> silence. Waiting for true IDLE instead wedges forever: with manual
turn detection + preemptive generation the session never returns to ``idle``
after the first wake word. ``_safe_to_warn`` is the event that captures the
real condition, driven by ``agent_state_changed`` + ``user_state_changed``.
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
# Max seconds a background follow-up waits for a safe gap per attempt (two
# attempts, then it drops with an ERROR). Bounds the wait so a dead session
# can never leak the background task. Generous: a spoken turn reply is ~3-5s.
_WAIT_SPEECH_END_TIMEOUT = 12.0
# Max seconds a deferred MODERATE waits for a safe gap (agent not generating +
# user not speaking) before dropping. Bounded so a deferred warning can't hang
# forever when the user keeps talking; the hazard loop re-defers on the next
# tick if the hazard persists, so dropping just yields this one attempt.
_MODERATE_WAIT_TIMEOUT = 6.0
# Max seconds a CRITICAL warning waits for reply_lock before firing unlocked.
# interrupt() cancels the current *speech* but NOT the background asyncio task
# holding the lock inside generate_reply — so without a bound, a CRITICAL
# warning can be delayed behind a slow follow-up. Life-safety > collision risk.
_CRITICAL_LOCK_TIMEOUT = 2.0


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
    1. Wait for a SAFE GAP (agent not generating/speaking its turn reply AND
       user not speaking) BEFORE firing. Two bounded attempts; if no gap opens
       the follow-up is DROPPED with an ERROR — firing into a collision
       produces overlapping generations (the 17s garbled-audio bug), which is
       worse than a drop the user can retry by re-asking.
    2. Acquire the per-session reply_lock so two follow-ups (or a follow-up and
       a hazard warning) can't both call generate_reply at once (the loser would
       time out waiting for generation_created -> 60s silence).

    Best-effort: dead-session (RuntimeError), timeout, and cancellation errors
    are logged and swallowed, never raised into the background task.
    """
    userdata = getattr(session, "userdata", None)
    lock = userdata.get("reply_lock") if isinstance(userdata, dict) else None
    # safe_to_warn_event is the real safe gap; not_speaking_event is the
    # weaker fallback (set during `thinking` too — can still race the turn
    # reply) used only when no PriorityManager published the safe event.
    safe_event = (
        userdata.get("safe_to_warn_event") if isinstance(userdata, dict) else None
    )
    not_speaking = (
        userdata.get("not_speaking_event") if isinstance(userdata, dict) else None
    )
    wait_event = safe_event or not_speaking
    t0 = time.monotonic()
    try:
        # Guard 1: bounded attempts at a safe gap. Bounded so a dead session
        # can't leak this background task forever on wait().
        if wait_event is not None:
            for attempt in (1, 2):
                try:
                    await asyncio.wait_for(
                        wait_event.wait(), timeout=_WAIT_SPEECH_END_TIMEOUT
                    )
                    break
                except TimeoutError:
                    logger.warning(
                        "[SERIALIZE-RACE] safe-gap wait TIMEOUT %.1fs (attempt %d/2)",
                        time.monotonic() - t0,
                        attempt,
                    )
            else:
                logger.error(
                    "[SERIALIZE-RACE] no safe gap after %.1fs — DROPPING "
                    "follow-up (firing would collide with the turn reply)",
                    time.monotonic() - t0,
                )
                return
        speech_wait = time.monotonic() - t0
        if speech_wait > 0.2:
            logger.info(
                "[SERIALIZE-RACE] waited %.2fs for safe gap before lock",
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
        # True when the agent is in a state where OUR generate_reply will not
        # collide with LiveKit's own turn reply OR clobber the user's speech:
        # agent state is listening/idle/initializing (NOT thinking/speaking) AND
        # the user is not currently speaking. This is the real "safe gap".
        # The session never reaches `idle` after the first wake word (manual
        # turn detection + preemptive generation keep it cycling
        # listening<->thinking<->speaking), so waiting on `idle` hangs forever
        # and waiting on `not_speaking` fires during `thinking` (races the turn
        # reply generation). `safe_to_warn` is what actually avoids both.
        self._agent_ready = True  # agent state in listening/idle/initializing
        self._user_speaking = False
        self._safe_to_warn = asyncio.Event()
        self._safe_to_warn.set()
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
        # Wake any waiter parked on _safe_to_warn so it exits via the
        # _stopped check instead of hanging on a dead session.
        self._safe_to_warn.set()
        self._cancel_deferred()

    def _update_safe(self) -> None:
        """Recompute the safe-gap event from the latest agent/user states."""
        if self._stopped:
            return
        if self._agent_ready and not self._user_speaking:
            self._safe_to_warn.set()
        else:
            self._safe_to_warn.clear()

    def attach(self, session: AgentSession) -> None:
        """Track agent + user state transitions so on_hazard knows when it is
        safe to interrupt, and so deferred hazards can wait for a safe gap."""

        @session.on("agent_state_changed")
        def _on_agent_state_changed(ev: Any) -> None:
            old = self._livekit_state
            new = ev.new_state
            self._livekit_state = new
            if new == "speaking":
                self._not_speaking.clear()
            elif old == "speaking":
                self._not_speaking.set()
            # thinking/speaking = LiveKit's own turn reply is being generated
            # or spoken — NOT safe for our generate_reply.
            self._agent_ready = new in ("listening", "idle", "initializing")
            self._update_safe()
            logger.debug(
                "[PRIORITY] state %s -> %s (design=%s)",
                old,
                new,
                self.design_state,
            )

        @session.on("user_state_changed")
        def _on_user_state_changed(ev: Any) -> None:
            self._user_speaking = ev.new_state == "speaking"
            self._update_safe()

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
            await self._speak(_hazard_instructions(hazard, urgent=True), critical=True)
        elif hazard.priority is HazardPriority.MODERATE:
            if not self._safe_to_warn.is_set():
                # No safe gap: the user's turn reply is being generated/spoken
                # OR the user is talking. Firing here would race LiveKit's own
                # turn reply (which does NOT take reply_lock) -> generation
                # timeout -> silence. Defer (bounded); the waiter fires when a
                # safe gap opens. CRITICAL still preempts via interrupt().
                logger.info(
                    "[HAZARD-RACE] defer MODERATE — state=%s kind=%r (wait for safe gap)",
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
        """Background waiter: speak the latest deferred MODERATE once a safe
        gap opens (agent not generating/speaking AND user not speaking),
        unless a CRITICAL preempts it or no gap opens within the bound.

        Bounded wait: on timeout the hazard is dropped — the hazard loop
        re-defers on its next tick if the hazard is still visible, so dropping
        only yields this one attempt. Unbounded would hang the waiter forever
        when the user keeps talking (the 111s wedge this replaces).
        """
        started = time.monotonic()
        try:
            async with asyncio.timeout(_MODERATE_WAIT_TIMEOUT):
                await self._safe_to_warn.wait()
        except TimeoutError:
            self._pending_moderate = None
            self._deferred_task = None
            logger.info(
                "[HAZARD-RACE] deferred MODERATE dropped after %.2fs — no safe "
                "gap (hazard loop re-defers if it persists)",
                time.monotonic() - started,
            )
            return
        except asyncio.CancelledError:
            cause = (
                "session stopped (disconnect)"
                if self._stopped
                else "CRITICAL preempted"
            )
            logger.info(
                "[HAZARD-RACE] deferred MODERATE cancelled (%s) after %.2fs",
                cause,
                time.monotonic() - started,
            )
            return
        if self._stopped:
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

    async def _speak(self, instructions: str, *, critical: bool = False) -> None:
        if self._stopped:
            return
        # Hold the reply lock so the hazard reply can't race a background
        # navigator/reasoning follow-up on the same Gemini Live session.
        t0 = time.monotonic()
        acquired = False
        try:
            if critical:
                # interrupt() does NOT cancel the background task holding the
                # lock inside generate_reply, so an unbounded wait can delay a
                # life-safety warning. Bound it; past the bound, fire unlocked.
                try:
                    async with asyncio.timeout(_CRITICAL_LOCK_TIMEOUT):
                        await self._reply_lock.acquire()
                        acquired = True
                except TimeoutError:
                    logger.error(
                        "[HAZARD-RACE] CRITICAL lock TIMEOUT %.1fs — firing "
                        "unlocked (life-safety overrides collision risk)",
                        time.monotonic() - t0,
                    )
            else:
                await self._reply_lock.acquire()
                acquired = True
            lock_wait = time.monotonic() - t0
            if acquired and lock_wait > 0.2:
                # Hazard warning blocked behind a wake/navigator/follow-up
                # reply. A long wait here means the safety warning was delayed.
                logger.warning(
                    "[HAZARD-RACE] %s lock wait=%.2fs — safety warning "
                    "delayed behind another reply",
                    "CRITICAL" if critical else "MODERATE",
                    lock_wait,
                )
            if self._stopped:
                return
            await self._session.generate_reply(instructions=instructions)
        except Exception as exc:
            logger.error(
                "[HAZARD-RACE] generate_reply failed after %.2fs — %s",
                time.monotonic() - t0,
                exc,
                exc_info=True,
            )
        finally:
            if acquired:
                self._reply_lock.release()


def attach_priority_manager(session: AgentSession) -> PriorityManager:
    """Create a PriorityManager for the session and wire its state tracker.

    Returns the manager so the caller can feed it hazards (e.g. from the
    hazard detection loop). Also publishes two coordination primitives on
    session.userdata so background follow-ups (navigator, reasoning) can avoid
    racing the agent's turn reply or each other:

    - "reply_lock": asyncio.Lock serializing every generate_reply on the session
    - "safe_to_warn_event": asyncio.Event set during a safe gap (agent not
      generating/speaking its turn reply AND user not speaking) — the primary
      condition background follow-ups wait on before firing.
    - "not_speaking_event": asyncio.Event set when the agent is NOT speaking.
      Weaker fallback (set during `thinking` too); only used when no
      PriorityManager is attached.
    """
    pm = PriorityManager(session)
    pm.attach(session)
    userdata = getattr(session, "userdata", None)
    if isinstance(userdata, dict):
        userdata["reply_lock"] = pm._reply_lock
        userdata["safe_to_warn_event"] = pm._safe_to_warn
        userdata["not_speaking_event"] = pm._not_speaking
    logger.info("PriorityManager attached — cooldown=%.1fs", _COOLDOWN)
    return pm


if __name__ == "__main__":
    # Self-check for the state machine (repo has no test suite; this is the
    # runnable check for the concurrency logic). Run:
    #   uv run python src/tuntun_agent/priority.py
    import logging
    from types import SimpleNamespace

    _MODERATE_WAIT_TIMEOUT = 0.3
    _CRITICAL_LOCK_TIMEOUT = 0.3

    class _FakeSession:
        def __init__(self) -> None:
            self.userdata: dict[str, Any] = {}
            self.replies: list[str] = []
            self.interrupts = 0
            self._handlers: dict[str, list[Any]] = {}

        def on(self, event: str) -> Any:
            def deco(fn: Any) -> Any:
                self._handlers.setdefault(event, []).append(fn)
                return fn

            return deco

        def emit(self, event: str, **kw: Any) -> None:
            for fn in self._handlers.get(event, []):
                fn(SimpleNamespace(**kw))

        async def generate_reply(self, instructions: str = "", **kw: Any) -> None:
            self.replies.append(instructions)

        async def interrupt(self) -> None:
            self.interrupts += 1

    def _pm(session: _FakeSession) -> PriorityManager:
        pm = PriorityManager(session)  # type: ignore[arg-type]
        pm.attach(session)  # type: ignore[arg-type]
        return pm

    async def _main() -> None:
        # A: MODERATE during agent speech defers, then fires on the safe gap.
        s = _FakeSession()
        pm = _pm(s)
        s.emit("agent_state_changed", old_state="listening", new_state="speaking")
        await pm.on_hazard(Hazard("pothole ahead", HazardPriority.MODERATE, "pothole"))
        assert s.replies == [], "A: MODERATE fired while agent speaking"
        s.emit("agent_state_changed", old_state="speaking", new_state="listening")
        await asyncio.sleep(0.1)
        assert len(s.replies) == 1, (
            f"A: deferred MODERATE did not fire on safe gap ({s.replies})"
        )
        print("PASS A: deferred MODERATE fires when safe gap opens")

        # B: no safe gap within the bound -> dropped, never fired.
        s = _FakeSession()
        pm = _pm(s)
        s.emit("user_state_changed", old_state="listening", new_state="speaking")
        await pm.on_hazard(
            Hazard("step down left", HazardPriority.MODERATE, "step_down")
        )
        await asyncio.sleep(0.6)
        assert s.replies == [], f"B: MODERATE fired without a safe gap ({s.replies})"
        print("PASS B: deferred MODERATE dropped after bounded wait")

        # C: CRITICAL preempts a deferred MODERATE and fires even while a
        # background follow-up holds reply_lock past the bounded wait.
        s = _FakeSession()
        pm = _pm(s)
        s.emit("agent_state_changed", old_state="listening", new_state="speaking")
        await pm.on_hazard(
            Hazard("gutter ahead", HazardPriority.MODERATE, "drainage_gutter")
        )
        await pm._reply_lock.acquire()
        await pm.on_hazard(
            Hazard("pit ahead", HazardPriority.CRITICAL, "excavation_pit")
        )
        assert len(s.replies) == 1 and "pit" in s.replies[0], (
            f"C: CRITICAL did not fire past held lock ({s.replies})"
        )
        assert s.interrupts == 1, "C: CRITICAL did not interrupt"
        pm._reply_lock.release()
        await asyncio.sleep(0.1)
        assert len(s.replies) == 1, (
            f"C: preempted MODERATE fired after CRITICAL ({s.replies})"
        )
        print("PASS C: CRITICAL preempts deferred MODERATE + held lock")

        # D: stop() during a deferral wakes the waiter; nothing fires after.
        s = _FakeSession()
        pm = _pm(s)
        s.emit("agent_state_changed", old_state="listening", new_state="speaking")
        await pm.on_hazard(
            Hazard("open manhole", HazardPriority.MODERATE, "open_manhole")
        )
        pm.stop()
        await asyncio.sleep(0.1)
        assert s.replies == [], f"D: fired after stop ({s.replies})"
        await pm.on_hazard(Hazard("vehicle", HazardPriority.CRITICAL, "vehicle"))
        assert s.replies == [], "D: on_hazard not a no-op after stop"
        print("PASS D: stop() cancels waiter and gates all later hazards")

    logging.basicConfig(level=logging.CRITICAL)
    asyncio.run(_main())
    print("priority.py self-check: ALL PASS")
