"""Capture clocks (BUILD.md §5.2).

SourceClock: steady first-sample times for one device from jittery callback times.
ChannelTimeline: places a channel's samples on the shared meeting timeline.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from evra.audio.frames import FRAME_SAMPLES, NS, SAMPLE_RATE, Int16Array


class SourceClock:
    def __init__(
        self,
        native_rate: int,
        *,
        latency_ns: int = 0,
        window: int = 100,
        jump_ns: int = 50_000_000,
        jump_chunks: int = 3,
    ) -> None:
        self._rate = native_rate
        self._latency_ns = latency_ns
        self._samples = 0
        self._recent: deque[float] = deque(maxlen=window)
        self._pending: list[float] = []
        self._anchor: float | None = None
        self._jump_ns = jump_ns
        self._jump_chunks = jump_chunks

    def first_sample_ns(self, t_callback_ns: int, frames: int) -> int:
        before = self._samples
        self._samples += frames
        implied = t_callback_ns - self._latency_ns - self._samples * NS / self._rate
        if self._anchor is None:
            self._anchor = implied
            self._recent.append(implied)
        elif implied - self._anchor > self._jump_ns:
            self._pending.append(implied)
            if len(self._pending) >= self._jump_chunks:
                self._anchor = min(self._pending)
                self._recent.clear()
                self._recent.extend(self._pending)
                self._pending.clear()
        else:
            self._pending.clear()
            self._recent.append(implied)
            self._anchor = min(self._recent)
        return round(self._anchor + before * NS / self._rate)


GAP_SAMPLES = 800  # 50 ms: a hole this big is a gap, filled at once
MAX_DRIFT_SAMPLES = 320  # 20 ms of drift before correcting
CHECK_EVERY_SAMPLES = SAMPLE_RATE  # compare clocks about once per second of audio
STEP = FRAME_SAMPLES  # corrections move in 10 ms steps


@dataclass(frozen=True)
class Gap:
    start: int  # timeline sample index
    length: int  # samples of inserted silence
    cause: str  # dropout | device_change | silence


@dataclass
class TimelineStats:
    corrections: int = 0
    inserted: int = 0
    dropped: int = 0
    padded: int = 0
    drift: int = 0  # samples; positive = timeline ahead of real time
    gaps: list[Gap] = field(default_factory=list)


class ChannelTimeline:
    def __init__(self, start_ns: int) -> None:
        self._start_ns = start_ns
        self.emitted = 0
        self.stats = TimelineStats()
        self._since_check = 0
        self._owed_drop = 0

    def index_at(self, t_ns: int) -> int:
        return round((t_ns - self._start_ns) * SAMPLE_RATE / NS)

    def place(self, samples: Int16Array, t_first_ns: int, cause: str = "dropout") -> Int16Array:
        """What to append to this channel's timeline for a chunk whose first sample is at t."""
        delta = self.index_at(t_first_ns) - self.emitted  # > 0: timeline behind real time
        out = samples
        if delta >= GAP_SAMPLES:
            fill = delta // STEP * STEP
            self.stats.gaps.append(Gap(self.emitted, fill, cause))
            self.stats.inserted += fill
            out = np.concatenate([np.zeros(fill, dtype=np.int16), out])
            self._since_check = 0
            self._owed_drop = 0
        elif self._since_check >= CHECK_EVERY_SAMPLES:
            self._since_check = 0
            if abs(delta) > MAX_DRIFT_SAMPLES:
                amount = abs(delta) // STEP * STEP
                self.stats.corrections += 1
                if delta > 0:
                    self.stats.inserted += amount
                    out = np.concatenate([np.zeros(amount, dtype=np.int16), out])
                else:
                    self._owed_drop += amount
        if self._owed_drop and len(out):
            cut = min(self._owed_drop, len(out))
            out = out[cut:]
            self._owed_drop -= cut
            self.stats.dropped += cut
        self._since_check += len(samples)
        self.emitted += len(out)
        self.stats.drift = self.emitted - (self.index_at(t_first_ns) + len(samples))
        return out

    def pad_until(self, now_ns: int, margin_ns: int = 100_000_000) -> Int16Array:
        """Silence that keeps the timeline moving while a source delivers nothing."""
        missing = self.index_at(now_ns - margin_ns) - self.emitted
        if missing < STEP:
            return np.zeros(0, dtype=np.int16)
        fill = missing // STEP * STEP
        self.stats.padded += fill
        self.emitted += fill
        return np.zeros(fill, dtype=np.int16)
