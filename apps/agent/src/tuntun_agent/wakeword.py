"""Wake word gating — "Hey Tutu" detection via openwakeword.

The agent is gated behind a wake word so it does NOT react to ambient speech
(the user talking to a companion, street vendors, etc.). Only after the user
says "Hey Tutu" does the agent open a listening window and respond.

Design
------
1. ``AgentSession`` is created with ``turn_detection="manual"`` — the session
   will NOT auto-detect end-of-turn from VAD. The agent stays silent until we
   explicitly open a turn.
2. This module subscribes to the user's microphone ``AudioTrack`` (16-bit PCM,
   resampled to 16 kHz mono) and feeds 80 ms chunks (1280 samples) into the
   openwakeword ONNX model ``hey_tutu.onnx``.
3. When the model score exceeds ``_WAKE_THRESHOLD`` for
   ``_WAKE_CONSECUTIVE_FRAMES`` consecutive frames, the wake word is
   considered detected.
4. On detection we:
     a. call ``session.interrupt()`` to stop any in-progress agent speech,
     b. call ``session.generate_reply`` with a short acknowledgment, which
        opens the mic for the user's next utterance.
5. A cooldown (``_WAKE_COOLDOWN``) prevents rapid re-triggering.

NOTE on proactive obstacle warnings under manual mode:
    Manual turn detection means Gemini will only "speak" when we call
    ``generate_reply``. To preserve proactive safety warnings (the core value
    of the Reflex Layer) without sacrificing wake-word gating, the detector
    periodically (every ``_PROACTIVE_INTERVAL``) opens a short proactive turn
    during which Gemini can emit any urgent obstacle warning it sees in the
    camera. This gives near-instant hazard alerts while still keeping the
    agent quiet during normal conversation.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from typing import Any

import numpy as np
from livekit import rtc
from livekit.agents import AgentSession

from tuntun_agent.logging_setup import get_logger

logger = get_logger()

# Hold strong references to fire-and-forget background tasks so they are not
# garbage-collected mid-run (ruff RUF006). Tasks self-remove on completion.
_background_tasks: set[asyncio.Task[Any]] = set()


def _spawn(coro: Any) -> asyncio.Task[Any]:
    """Schedule a fire-and-forget task and keep a strong ref to it."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


# openwakeword expects 1280-sample chunks (80 ms @ 16 kHz).
_OPENWAKEWORD_CHUNK_SAMPLES = 1280
_OPENWAKEWORD_SAMPLE_RATE = 16000

# Score above which a frame is considered "wake-like".
_WAKE_THRESHOLD = 0.5
# Number of consecutive above-threshold frames required to fire.
_WAKE_CONSECUTIVE_FRAMES = 3
# Seconds after a detection before we accept another.
_WAKE_COOLDOWN = 3.0
# Seconds between proactive "safety check" turns so Gemini can warn about
# obstacles even when the user hasn't said the wake word recently.
_PROACTIVE_INTERVAL = 12.0

# Path to the bundled ONNX wake-word model relative to the package src root.
_MODEL_PATH = Path(__file__).resolve().parent.parent / "onnx" / "hey_tutu.onnx"


class HeyTutuDetector:
    """Wake-word detector that gates an AgentSession behind "Hey Tutu".

    Instantiate after the session is created and the room is connected, then
    ``await detector.start(room)``. Call ``await detector.stop()`` on exit.
    """

    def __init__(self, session: AgentSession) -> None:
        self._session = session
        self._model: Any = None
        self._audio_stream: rtc.AudioStream | None = None
        self._task: asyncio.Task[Any] | None = None
        self._proactive_task: asyncio.Task[Any] | None = None
        self._consecutive = 0
        self._last_wake = 0.0
        self._stopped = False
        # Buffer for accumulating 16 kHz samples until we have a full chunk.
        self._pcm_buffer = np.empty(0, dtype=np.int16)

    async def _load_model(self) -> None:
        """Lazy-import openwakeword and load the ONNX model."""
        if not _MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Wake word model not found at {_MODEL_PATH}. "
                "Expected apps/agent/src/onnx/hey_tutu.onnx"
            )
        # Imported here so the module imports even if openwakeword /
        # onnxruntime are not yet installed (graceful degradation).
        from openwakeword.model import Model

        # openwakeword's AudioFeatures preprocessor needs the melspectrogram
        # and embedding ONNX models in its resources/models/ directory. These
        # are NOT shipped in the wheel and must be downloaded once. We ensure
        # they exist before constructing the Model.
        await self._ensure_preprocessor_models()

        self._model = Model(wakeword_models=[str(_MODEL_PATH)])
        model_names = list(self._model.models.keys())
        logger.info(
            "Wake word model loaded — path=%s model_name=%s",
            _MODEL_PATH,
            model_names[0] if model_names else "<none>",
        )

    async def _ensure_preprocessor_models(self) -> None:
        """Ensure openwakeword's melspectrogram + embedding ONNX models are
        present. These are downloaded on first run (not shipped in the wheel).
        Runs in a thread so the synchronous download doesn't block the loop."""
        import functools
        import inspect
        import os as _os
        import pathlib

        from openwakeword.utils import download_models

        utils_module = inspect.getmodule(download_models)
        assert utils_module is not None
        utils_file = pathlib.Path(utils_module.__file__)
        resources_dir = utils_file.parent / "resources" / "models"
        needed = ["melspectrogram.onnx", "embedding_model.onnx"]
        missing = [f for f in needed if not (resources_dir / f).exists()]
        if not missing:
            return
        logger.info(
            "Wake word: downloading openwakeword preprocessor models "
            "(missing: %s) — one-time setup",
            ", ".join(missing),
        )

        def _do_download() -> None:
            _os.makedirs(resources_dir, exist_ok=True)
            # download_models() fetches the preprocessor models + all wake
            # word models. We only need the preprocessors, but calling with
            # an empty list is the simplest reliable path.
            download_models(model_names=[])

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, functools.partial(_do_download))
        logger.info("Wake word: preprocessor models downloaded")

    def _find_mic_track(self, room: rtc.Room) -> rtc.Track | None:
        """Find the first published microphone audio track from a remote
        participant. Returns None if not yet published."""
        for participant in room.remote_participants.values():
            for publication in participant.track_publications.values():
                track = publication.track
                if track is None:
                    continue
                if track.kind == rtc.TrackKind.KIND_AUDIO:
                    logger.info(
                        "Wake word: found mic track — participant=%s track=%s",
                        participant.identity,
                        getattr(track, "sid", "?"),
                    )
                    return track

    async def start(self, room: rtc.Room) -> None:
        """Begin listening for the wake word. Subscribes to the user's mic
        track (now or when it arrives) and starts the detection loop."""
        try:
            await self._load_model()
        except Exception as exc:
            logger.error(
                "Wake word: failed to load model — gating disabled: %s",
                exc,
                exc_info=True,
            )
            return

        track = self._find_mic_track(room)
        if track is not None:
            self._attach_track(track)
        else:
            logger.info("Wake word: no mic track yet — waiting for track_subscribed")

        @room.on("track_subscribed")
        def _on_track_subscribed(t, publication, participant):
            if t.kind == rtc.TrackKind.KIND_AUDIO:
                self._attach_track(t)

        @room.on("track_unsubscribed")
        def _on_track_unsubscribed(t, publication, participant):
            if t.kind == rtc.TrackKind.KIND_AUDIO:
                self._detach_track()

        # Start the proactive safety-check loop.
        self._proactive_task = asyncio.create_task(self._proactive_loop())

    def _attach_track(self, track: rtc.Track) -> None:
        """Open an AudioStream on the mic track at 16 kHz mono."""
        if self._audio_stream is not None:
            return  # already attached
        try:
            self._audio_stream = rtc.AudioStream(
                track,
                sample_rate=_OPENWAKEWORD_SAMPLE_RATE,
                num_channels=1,
            )
            self._task = asyncio.create_task(self._detect_loop())
            logger.info("Wake word: detection loop started")
        except Exception as exc:
            logger.error(
                "Wake word: failed to open AudioStream: %s", exc, exc_info=True
            )

    def _detach_track(self) -> None:
        """Stop the detection loop and close the audio stream."""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._audio_stream is not None:
            _spawn(self._audio_stream.aclose())
            self._audio_stream = None
        logger.info("Wake word: detection loop stopped")

    async def _detect_loop(self) -> None:
        """Read 16 kHz PCM from the mic, feed 1280-sample chunks to the
        openwakeword model, and fire on detection."""
        assert self._audio_stream is not None
        assert self._model is not None
        logger.info("Wake word detect loop running — threshold=%.2f", _WAKE_THRESHOLD)
        try:
            async for frame in self._audio_stream:
                if self._stopped:
                    break
                # frame.data is int16 PCM at 16 kHz mono.
                pcm = np.frombuffer(frame.data, dtype=np.int16)
                self._pcm_buffer = np.concatenate([self._pcm_buffer, pcm])
                # Process full 1280-sample chunks.
                while len(self._pcm_buffer) >= _OPENWAKEWORD_CHUNK_SAMPLES:
                    chunk = self._pcm_buffer[:_OPENWAKEWORD_CHUNK_SAMPLES]
                    self._pcm_buffer = self._pcm_buffer[_OPENWAKEWORD_CHUNK_SAMPLES:]
                    self._process_chunk(chunk)
        except asyncio.CancelledError:
            logger.info("Wake word detect loop cancelled")
        except Exception as exc:
            logger.error("Wake word detect loop error: %s", exc, exc_info=True)

    def _process_chunk(self, chunk: np.ndarray) -> None:
        """Run the model on one 1280-sample chunk and check for a wake word."""
        try:
            scores = self._model.predict(chunk)
        except Exception as exc:
            logger.error("Wake word predict failed: %s", exc, exc_info=True)
            return

        score = 0.0
        if isinstance(scores, dict):
            for v in scores.values():
                score = float(v)
                break
        else:
            score = float(scores)

        now = time.monotonic()
        if score >= _WAKE_THRESHOLD:
            self._consecutive += 1
        else:
            self._consecutive = 0

        if (
            self._consecutive >= _WAKE_CONSECUTIVE_FRAMES
            and (now - self._last_wake) > _WAKE_COOLDOWN
        ):
            self._consecutive = 0
            self._last_wake = now
            logger.info(
                "Wake word DETECTED — 'Hey Tutu' score=%.3f consecutive=%d",
                score,
                _WAKE_CONSECUTIVE_FRAMES,
            )
            _spawn(self._on_wake_word())

    async def _on_wake_word(self) -> None:
        """Called when the wake word fires: interrupt any speech and open a
        listening turn for the user's command."""
        try:
            await self._session.interrupt()
        except Exception as exc:
            logger.warning("Wake word: interrupt failed: %s", exc)
        try:
            await self._session.generate_reply(
                instructions=(
                    "The user just said your wake word, 'Hey Tutu'. "
                    "Acknowledge briefly (one short phrase like 'Yes?' or "
                    "'I'm here') and then listen for their request."
                ),
            )
            logger.info("Wake word: listening turn opened")
        except Exception as exc:
            logger.error("Wake word: generate_reply failed: %s", exc, exc_info=True)

    async def _proactive_loop(self) -> None:
        """Periodically open a short proactive turn so Gemini can emit urgent
        obstacle warnings from the camera even when the user hasn't said the
        wake word. This preserves the Reflex Layer's safety value under
        manual turn detection."""
        logger.info(
            "Wake word proactive safety loop started — interval=%.0fs",
            _PROACTIVE_INTERVAL,
        )
        try:
            while not self._stopped:
                await asyncio.sleep(_PROACTIVE_INTERVAL)
                if self._stopped:
                    break
                now = time.monotonic()
                # Skip if the user spoke recently (a real turn just happened).
                if (now - self._last_wake) < _PROACTIVE_INTERVAL:
                    continue
                try:
                    await self._session.generate_reply(
                        instructions=(
                            "Proactive safety check: silently scan the camera "
                            "feed for any IMMEDIATE danger to the user (obstacle "
                            "in their path, drop, oncoming vehicle, fall). If "
                            "there IS urgent danger, give a short spatial "
                            "warning now. If there is NO immediate danger, say "
                            "nothing and do not speak — stay silent. Do not "
                            "narrate or comment unless there is a real hazard."
                        ),
                    )
                    logger.debug("Wake word: proactive safety check dispatched")
                except Exception as exc:
                    logger.debug("Wake word: proactive check skipped: %s", exc)
        except asyncio.CancelledError:
            logger.info("Wake word proactive loop cancelled")

    async def stop(self) -> None:
        """Stop all loops and clean up."""
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._proactive_task is not None:
            self._proactive_task.cancel()
            self._proactive_task = None
        if self._audio_stream is not None:
            with contextlib.suppress(Exception):
                await self._audio_stream.aclose()
            self._audio_stream = None
        logger.info("Wake word detector stopped")


def attach_wake_word(session: AgentSession, room: rtc.Room) -> HeyTutuDetector:
    """Create and start a HeyTutuDetector for the given session + room.

    Returns the detector so the caller can ``await detector.stop()`` on exit.
    """
    detector = HeyTutuDetector(session)
    _spawn(detector.start(room))
    return detector
