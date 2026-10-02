"""One live 1:1 recording: capture -> voice detection -> live transcript (M3a), shared by
`evra record` and the window (M3c spec §3.1).

Capture opens first and the meeting is created only once it runs, so a missing or busy
microphone never leaves an empty meeting behind. Segments cut in the moment before the
transcriber exists are held and handed over in order.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from evra.asr.parakeet import PARAKEET_ID
from evra.audio.frames import Frames, Int16Array
from evra.audio.vad import SpeechSegment, SpeechSegmenter, silero_vad
from evra.capture.devices import refresh_devices, resolve_mic
from evra.capture.session import CaptureHealth, CaptureSession
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance, now_ms
from evra.transcribe.cli import ensure_speech_models
from evra.transcribe.live import LiveTranscriber, TranscriberStats
from evra.workers.asr import AsrClient, Transcriber

SILENCE_DB = -60.0
UtteranceListener = Callable[[Utterance], None]
LevelListener = Callable[[int, float], None]


@dataclass(frozen=True)
class RecordingResult:
    meeting_id: str
    utterances: int
    health: CaptureHealth | None
    stats: TranscriberStats
    interrupted: bool


def frame_level(pcm: Int16Array) -> float:
    """Loudness of one frame on 0..1 (-60 dBFS -> 0, 0 dBFS -> 1) for the level meters.
    Only this number leaves the capture thread, never the audio."""
    if len(pcm) == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(pcm.astype(np.float32) / 32768.0))))
    if rms <= 1e-6:
        return 0.0
    db = 20 * math.log10(rms)
    return min(1.0, max(0.0, (db - SILENCE_DB) / -SILENCE_DB))


class LiveRecording:
    def __init__(
        self,
        *,
        session: CaptureSession,
        segmenters: Mapping[int, SpeechSegmenter],
        asr: Transcriber,
        db_path: Path,
        title: str,
        situation: str,
        on_utterance: UtteranceListener | None = None,
        on_level: LevelListener | None = None,
    ) -> None:
        self._session = session
        self._segmenters = segmenters
        self._asr = asr
        self._db_path = db_path
        self._title = title
        self._situation = situation
        self._on_utterance = on_utterance
        self._on_level = on_level
        self._lock = threading.Lock()
        self._live: LiveTranscriber | None = None
        self._pending: list[SpeechSegment] = []
        self.meeting_id: str | None = None
        self.started_at_ms: int | None = None

    def _on_frames(self, frames: Frames) -> None:  # runs on the capture pipeline thread
        if self._on_level is not None:
            self._on_level(frames.channel, frame_level(frames.pcm))
        for segment in self._segmenters[frames.channel].accept(frames):
            with self._lock:
                if self._live is None:
                    self._pending.append(segment)
                    continue
                live = self._live
            live.submit(segment)

    def start(self) -> str:
        self._session.start(self._on_frames)  # a missing or busy mic fails here: no meeting yet
        try:
            started = now_ms()
            conn = connect(self._db_path)
            try:
                store = MeetingStore(conn)
                meeting_id = store.create_meeting(
                    title=self._title,
                    mode="one_on_one",
                    situation=self._situation,
                    template="one_on_one",
                    started_at_ms=started,
                )
                version_id = store.create_transcript_version(
                    meeting_id, kind="live", model=PARAKEET_ID
                )
            finally:
                conn.close()
            live = LiveTranscriber(
                self._asr, self._db_path, meeting_id=meeting_id, version_id=version_id
            )
            if self._on_utterance is not None:
                live.add_listener(self._on_utterance)
            live.start()
        except BaseException:
            self._session.stop()
            raise
        with self._lock:  # hand held segments over in order, before any newer one
            self._live = live
            for segment in self._pending:
                live.submit(segment)
            self._pending = []
        self.meeting_id, self.started_at_ms = meeting_id, started
        return meeting_id

    def stop(self, *, state: str = "ready") -> RecordingResult:
        live, meeting_id = self._live, self.meeting_id
        if live is None or meeting_id is None:
            raise RuntimeError("the recording has not started")
        health: CaptureHealth | None = None
        try:
            health = self._session.stop()
            for segmenter in self._segmenters.values():
                for segment in segmenter.flush():
                    live.submit(segment)
        finally:  # whatever capture did, keep the queued speech and finish the meeting
            stats = live.stop()
            conn = connect(self._db_path)
            try:
                MeetingStore(conn).finish_meeting(meeting_id, state=state)
            finally:
                conn.close()
        return RecordingResult(meeting_id, stats.utterances, health, stats, False)


class RecordingKit:
    """What a live recording needs, loaded once and kept: speech models, the ASR worker, VAD."""

    def __init__(self, paths: AppPaths, *, asr: AsrClient | None = None) -> None:
        self._paths = paths
        self._asr = asr or AsrClient.for_models(paths.models_dir)
        self._vad_path: Path | None = None
        self._lock = threading.Lock()

    def prepare(self) -> None:
        """Download (first run) and load what recording needs: slow once, then instant."""
        with self._lock:
            if self._vad_path is not None:
                return
            models = ensure_speech_models(self._paths)
            self._asr.warm_up()
            self._vad_path = models["silero-vad"] / "silero_vad.onnx"

    def new_recording(
        self,
        mic: int | str | None,
        *,
        title: str,
        situation: str,
        on_utterance: UtteranceListener | None = None,
        on_level: LevelListener | None = None,
    ) -> LiveRecording:
        from evra.capture.mic import MicSource
        from evra.capture.windows import DefaultOutputWatcher, LoopbackSource

        self.prepare()
        vad_path = self._vad_path
        assert vad_path is not None
        refresh_devices()  # see mics connected since start-up; nothing records yet
        device = mic if isinstance(mic, int) else resolve_mic(mic or "")
        session = CaptureSession(
            MicSource(device), LoopbackSource(), watcher_factory=DefaultOutputWatcher
        )
        segmenters = {ch: SpeechSegmenter(ch, silero_vad(vad_path)) for ch in (0, 1)}
        return LiveRecording(
            session=session,
            segmenters=segmenters,
            asr=self._asr,
            db_path=self._paths.db_path,
            title=title,
            situation=situation,
            on_utterance=on_utterance,
            on_level=on_level,
        )

    def close(self) -> None:
        self._asr.stop()
