"""Replays audio like a real device: 10 ms chunks, real-time pacing, injected faults (§5.1)."""

from __future__ import annotations

import threading
import time
import wave
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from evra.audio.frames import NS, Float32Array
from evra.audio.ringbuffer import ChunkRing


@dataclass(frozen=True)
class FakeEvent:
    kind: Literal["silence", "dropout"]  # silence: zeros delivered; dropout: nothing delivered
    start_s: float
    duration_s: float

    def covers(self, sample: int, rate: int) -> bool:
        """Compare in whole samples: float seconds (0.2 + 0.1) would misclassify edges."""
        first = round(self.start_s * rate)
        return first <= sample < first + round(self.duration_s * rate)


class FakeSource:
    def __init__(
        self,
        audio: Float32Array,
        rate: int,
        *,
        name: str = "fake",
        events: Sequence[FakeEvent] = (),
        pads_silence: bool = False,
        now_ns: Callable[[], int] = time.monotonic_ns,
        sleep: Callable[[float], None] = time.sleep,
        latency_ns: int = 0,
    ) -> None:
        self.audio = audio if audio.ndim == 2 else audio[:, None]
        self.name = name
        self.native_rate = rate
        self.native_channels = int(self.audio.shape[1])
        self.latency_ns = latency_ns
        self.pads_silence = pads_silence
        self.overflows = 0
        self.ring = ChunkRing.for_duration(2.0, 0.01)
        self.finished = threading.Event()
        self._events = tuple(events)
        self._now = now_ns
        self._sleep = sleep
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @classmethod
    def from_wav(cls, path: Path, **kwargs: Any) -> FakeSource:
        with wave.open(str(path), "rb") as w:
            if w.getsampwidth() != 2:
                raise ValueError(f"{path.name}: only 16-bit PCM WAV is supported")
            channels, rate = w.getnchannels(), w.getframerate()
            raw = w.readframes(w.getnframes())
        pcm = np.frombuffer(raw, dtype="<i2").reshape(-1, channels)
        return cls((pcm / 32768.0).astype(np.float32), rate, name=path.name, **kwargs)

    def chunks(self) -> Iterator[tuple[float, Float32Array | None]]:
        step = self.native_rate // 100
        for start in range(0, len(self.audio), step):
            t_s = start / self.native_rate
            chunk: Float32Array | None = self.audio[start : start + step]
            for event in self._events:
                if event.covers(start, self.native_rate):
                    chunk = None if event.kind == "dropout" else np.zeros_like(chunk)
            yield t_s, chunk

    def start(self) -> None:
        self._stop.clear()
        self.finished.clear()
        self._thread = threading.Thread(target=self._run, name=f"fake-{self.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        self._thread = None

    def reopen(self) -> None:
        self.stop()
        self.start()

    def _run(self) -> None:
        t0 = self._now()
        for t_s, chunk in self.chunks():
            if self._stop.is_set():
                break
            if chunk is None:
                continue
            due = t0 + int((t_s + len(chunk) / self.native_rate) * NS)
            wait = due - self._now()
            if wait > 0:
                self._sleep(wait / NS)
            self.ring.put(chunk.copy(), self._now())
        self.finished.set()
