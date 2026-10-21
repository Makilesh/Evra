"""Capture clocks (BUILD.md §5.2).

SourceClock: steady first-sample times for one device from jittery callback times.
ChannelTimeline: places a channel's samples on the shared meeting timeline.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from evra.audio.frames import FRAME_SAMPLES, NS, SAMPLE_RATE, Int16Array


@dataclass(frozen=True)
class Timed:
    """A chunk whose first-sample time is now known."""

    key: int
    t_first_ns: int
    jumped: bool  # first chunk after a confirmed jump (samples really missing / device idle)


@dataclass(frozen=True)
class _Held:
    key: int
    implied: float
    samples_before: int
    t_callback_ns: int


class SourceClock:
    """Steady first-sample times for one device from jittery callback times.

    Every chunk implies an anchor: callback time - latency - all samples so far / rate.
    Callbacks are only ever late, so the smallest recent anchor is the best estimate.

    A chunk more than `jump_ns` late is *held* until the clock can tell why:
    - a stall: a backlog burst (same callback time) that soon returns to normal lateness —
      released on the old anchor, nothing lost;
    - a jump: late chunks keep arriving at a normal pace for `confirm_ns` of audio (samples
      were lost, or loopback went idle) — released on the new anchor, placed at their true time.
    Holding costs at most ~`confirm_ns` of latency, only while a jump is suspected.
    The first `warmup_ns` of audio is also held, so a slow first callback cannot skew the
    anchor (it would otherwise be corrected later by dropping real audio).
    """

    def __init__(
        self,
        native_rate: int,
        *,
        latency_ns: int = 0,
        window: int = 100,
        jump_ns: int = 50_000_000,
        confirm_ns: int = 150_000_000,
        max_hold_ns: int = 1_000_000_000,
        warmup_ns: int = 200_000_000,
    ) -> None:
        self._rate = native_rate
        self._latency_ns = latency_ns
        self._samples = 0
        self._recent: deque[float] = deque(maxlen=window)
        self._anchor: float | None = None
        self._held: list[_Held] = []
        self._held_ns = 0.0
        self._jump_ns = jump_ns
        self._confirm_ns = confirm_ns
        self._max_hold_ns = max_hold_ns
        self._warmup_ns = warmup_ns

    def push(self, key: int, t_callback_ns: int, frames: int) -> list[Timed]:
        """Add a chunk; returns every chunk whose time is now decided, in order."""
        before = self._samples
        self._samples += frames
        implied = t_callback_ns - self._latency_ns - self._samples * NS / self._rate
        if self._anchor is None:  # warm-up: anchor on the earliest of the first chunks
            self._hold(key, implied, before, t_callback_ns, frames)
            if self._held_ns >= self._warmup_ns:
                return self._release(reanchor=True, jumped=False)
            return []
        if implied - self._anchor > self._jump_ns:
            self._hold(key, implied, before, t_callback_ns, frames)
            span = t_callback_ns - self._held[0].t_callback_ns
            confirmed = self._held_ns >= self._confirm_ns and span >= self._confirm_ns / 2
            if confirmed or self._held_ns >= self._max_hold_ns:
                return self._release(reanchor=True, jumped=True)
            return []
        out = self._release(reanchor=False, jumped=False)
        self._recent.append(implied)
        self._anchor = min(self._recent)
        out.append(self._timed(key, before, jumped=False))
        return out

    def flush(self) -> list[Timed]:
        """Decide any held chunks now (end of capture, device swap): keep the old anchor."""
        return self._release(reanchor=False, jumped=False)

    def _hold(self, key: int, implied: float, before: int, t_callback_ns: int, frames: int) -> None:
        self._held.append(_Held(key, implied, before, t_callback_ns))
        self._held_ns += frames * NS / self._rate

    def _release(self, *, reanchor: bool, jumped: bool) -> list[Timed]:
        if not self._held:
            return []
        if reanchor or self._anchor is None:
            self._anchor = min(h.implied for h in self._held)
            self._recent.clear()
            self._recent.extend(h.implied for h in self._held)
        out = [
            self._timed(h.key, h.samples_before, jumped=jumped and i == 0)
            for i, h in enumerate(self._held)
        ]
        self._held.clear()
        self._held_ns = 0.0
        return out

    def _timed(self, key: int, samples_before: int, *, jumped: bool) -> Timed:
        assert self._anchor is not None
        return Timed(key, round(self._anchor + samples_before * NS / self._rate), jumped)


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

    def place(self, samples: Int16Array, t_first_ns: int, cause: str | None = None) -> Int16Array:
        """What to append to this channel's timeline for a chunk whose first sample is at t."""
        delta = self.index_at(t_first_ns) - self.emitted  # > 0: timeline behind real time
        out = samples
        if self.emitted == 0 and self.stats.padded == 0:  # first audio on this channel
            return self._place_first(samples, t_first_ns, delta, cause)
        if delta >= GAP_SAMPLES:
            fill = delta // STEP * STEP
            self.stats.gaps.append(Gap(self.emitted, fill, cause or "dropout"))
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

    def _place_first(
        self, samples: Int16Array, t_first_ns: int, delta: int, cause: str | None
    ) -> Int16Array:
        """Align the channel's first chunk: trim audio from before the start, or lead with
        silence if the device started late (a gap only if audio was known to be lost)."""
        if delta < 0:
            out = samples[min(-delta, len(samples)) :]
        else:
            lead = delta // STEP * STEP
            if cause is not None and lead >= GAP_SAMPLES:
                self.stats.gaps.append(Gap(0, lead, cause))
                self.stats.inserted += lead
            else:
                self.stats.padded += lead
            out = np.concatenate([np.zeros(lead, dtype=np.int16), samples])
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
