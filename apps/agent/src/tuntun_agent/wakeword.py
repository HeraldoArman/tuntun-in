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

NOTE on proactive obstacle warnings:
    This module handles ONLY reactive conversation (wake word -> open turn).
    Proactive hazard warnings are owned by the separate Hazard Detection Loop
    (``hazard_loop.py``) + ``PriorityManager``, which bypass the wake gate and
    classify/interrupt with 3-level priority. Keeping the two trigger sources
    independent is the core of the design doc's dual-trigger architecture.
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
# Number of consecutive above-threshold frames required to fire. 2 frames =
# 160ms; lower than this rises false positives, higher adds detect latency.
_WAKE_CONSECUTIVE_FRAMES = 2
# Seconds after a detection before we accept another.
_WAKE_COOLDOWN = 3.0

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
        """Called when the wake word fires: interrupt any in-progress speech and
        answer the user's request in a single reply (no ack round trip).

        Latency-critical: the old flow spoke an acknowledgment ('Yes?') first,
        then listened — that doubled round trips (~1-2s extra). Now one
        ``generate_reply`` answers the request directly. The user should say the
        wake word + their request in one utterance ('Hey Tutu, what's ahead?').
        If they only said the wake word, fall back to a short 'Yes?'.
        """
        # Only interrupt if the agent is currently speaking — when idle (the
        # common wake case) interrupt is a wasted round trip.
        state = getattr(
            self._session.agent_state, "value", str(self._session.agent_state)
        )
        if state == "speaking":
            try:
                await self._session.interrupt()
            except Exception as exc:
                logger.warning("Wake word: interrupt failed: %s", exc)
        try:
            await self._session.generate_reply(
                instructions=(
                    "The user just said your wake word 'Hey Tutu' followed by "
                    "their request. Answer their request directly and concisely "
                    "in one short reply. Do NOT say 'yes', 'I'm here', or any "
                    "acknowledgment first — that wastes a turn. If the user only "
                    "said the wake word with no request, reply with just 'Yes?'."
                ),
            )
            logger.info("Wake word: reply turn opened")
        except Exception as exc:
            logger.error("Wake word: generate_reply failed: %s", exc, exc_info=True)

    async def stop(self) -> None:
        """Stop all loops and clean up."""
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            self._task = None
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
