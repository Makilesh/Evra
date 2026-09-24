"""Capture clocks (BUILD.md §5.2).

SourceClock: steady first-sample times for one device from jittery callback times.
ChannelTimeline: places a channel's samples on the shared meeting timeline.
"""

from __future__ import annotations

from collections import deque

from evra.audio.frames import NS


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
