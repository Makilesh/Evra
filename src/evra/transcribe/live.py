"""Live pass (BUILD.md §6.2): speech segments in, stored utterances out, in order."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import structlog

from evra.asr.engine import Word
from evra.audio.vad import SpeechSegment
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.workers.asr import Transcriber
from evra.workers.protocol import WorkerCrashed

log = structlog.get_logger(__name__)
UtteranceListener = Callable[[Utterance], None]
_STOP = object()


@dataclass(frozen=True)
class TranscriberStats:
    segments: int
    utterances: int
    failures: int
    audio_ms: int
    asr_ms: int

    @property
    def rtf(self) -> float:
        return self.asr_ms / self.audio_ms if self.audio_ms else 0.0


class LiveTranscriber:
    def __init__(
        self, asr: Transcriber, db_path: Path, *, meeting_id: str, version_id: str
    ) -> None:
        self._asr = asr
        self._db_path = db_path
        self._meeting_id = meeting_id
        self._version_id = version_id
        self._queue: queue.Queue[object] = queue.Queue()
        self._listeners: list[UtteranceListener] = []
        self._thread: threading.Thread | None = None
        self._segments = self._utterances = self._failures = 0
        self._audio_ms = self._asr_ms = 0

    def add_listener(self, listener: UtteranceListener) -> None:
        self._listeners.append(listener)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="live-transcriber", daemon=True)
        self._thread.start()

    def submit(self, segment: SpeechSegment) -> None:
        self._queue.put(segment)

    def stop(self, timeout_s: float = 120.0) -> TranscriberStats:
        self._queue.put(_STOP)
        if self._thread is not None:
            self._thread.join(timeout_s)
            self._thread = None
        return self.stats()

    def stats(self) -> TranscriberStats:
        return TranscriberStats(
            self._segments, self._utterances, self._failures, self._audio_ms, self._asr_ms
        )

    def _run(self) -> None:
        conn = connect(self._db_path)
        store = MeetingStore(conn)
        try:
            while (item := self._queue.get()) is not _STOP:
                assert isinstance(item, SpeechSegment)
                self._handle(store, item)
        finally:
            conn.close()

    def _handle(self, store: MeetingStore, segment: SpeechSegment) -> None:
        self._segments += 1
        self._audio_ms += segment.end_ms - segment.start_ms
        started = time.perf_counter()
        try:
            try:
                results = self._asr.transcribe(segment.pcm)
            except (
                WorkerCrashed,
                TimeoutError,
            ):  # a crashed or hung worker is replaced: retry once
                results = self._asr.transcribe(segment.pcm)
        except Exception as exc:
            self._failures += 1
            log.warning("transcription_failed", error=type(exc).__name__, channel=segment.channel)
            return
        finally:
            self._asr_ms += int((time.perf_counter() - started) * 1000)
        offset = segment.start_ms
        for result in results:
            if not result.text:
                continue
            utterance = store.add_utterance(
                version_id=self._version_id,
                meeting_id=self._meeting_id,
                channel=segment.channel,
                start_ms=offset + result.start_ms,
                end_ms=offset + result.end_ms,
                text=result.text,
                words=tuple(
                    Word(offset + w.start_ms, offset + w.end_ms, w.text) for w in result.words
                ),
            )
            self._utterances += 1
            for listener in self._listeners:
                try:
                    listener(utterance)
                except Exception as exc:  # a broken listener must not stop transcription
                    log.warning("utterance_listener_failed", error=type(exc).__name__)
