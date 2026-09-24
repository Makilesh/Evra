"""Per-channel drain → timestamp → convert → place → emit, every 10 ms (BUILD.md §5.2)."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from evra.audio.clock import ChannelTimeline, Gap, SourceClock
from evra.audio.convert import ToMono16k
from evra.audio.frames import FRAME_SAMPLES, NS, SAMPLE_RATE, Channel, Frames, Int16Array
from evra.capture.sources import AudioSource

SILENCE_AFTER_NS = 50_000_000  # no loopback data for 50 ms → pad silence (§5.1)
_FULL_SCALE = 32767.0


def _dbfs(ratio: float) -> float:
    return round(20 * math.log10(ratio), 2) if ratio > 0 else -120.0


@dataclass(frozen=True)
class ChannelStats:
    channel: int
    native_rate: int
    native_channels: int
    seconds: float
    rms_dbfs: float
    peak_dbfs: float
    dropped_chunks: int
    corrections: int
    inserted_ms: float
    dropped_ms: float
    padded_ms: float
    drift_ms: float
    gaps: tuple[Gap, ...]


class _ChannelState:
    def __init__(self, source: AudioSource, start_ns: int) -> None:
        self.source = source
        self.timeline = ChannelTimeline(start_ns)
        self.buffer: Int16Array = np.zeros(0, dtype=np.int16)
        self.frames_out = 0
        self.last_chunk_ns: int | None = None
        self.padding = False
        self.next_cause: str | None = None
        self.next_seq = 0  # ring sequence expected next; a jump means chunks were lost
        self.sum_squares = 0.0
        self.measured = 0
        self.peak = 0
        self.reset_format()

    def reset_format(self) -> None:
        self.converter = ToMono16k(self.source.native_rate, self.source.native_channels)
        self.clock = SourceClock(self.source.native_rate, latency_ns=self.source.latency_ns)


class CapturePipeline:
    def __init__(
        self,
        sources: Mapping[Channel, AudioSource],
        on_frames: Callable[[Frames], None],
        *,
        start_ns: int,
        now_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._start_ns = start_ns
        self._now = now_ns
        self._on_frames = on_frames
        self._states = {ch: _ChannelState(src, start_ns) for ch, src in sources.items()}
        self._lock = threading.Lock()

    def step(self) -> None:
        with self._lock:
            now = self._now()
            for channel, state in self._states.items():
                self._drain(state)
                self._maybe_pad(state, now)
                self._emit(channel, state)

    def flush(self) -> None:
        self.step()
        with self._lock:
            for channel, state in self._states.items():
                rest = len(state.buffer) % FRAME_SAMPLES
                if rest:
                    pad = np.zeros(FRAME_SAMPLES - rest, dtype=np.int16)
                    state.buffer = np.concatenate([state.buffer, pad])
                self._emit(channel, state)

    def swap_source(self, channel: Channel, cause: str = "device_change") -> None:
        """Re-open a source (e.g. new default output) without losing the timeline.

        Order matters: stop the old stream first (PortAudio may deliver one last buffer
        while stopping), drain everything in the old format, then start the new stream.
        """
        with self._lock:
            state = self._states[channel]
            state.source.stop()
            self._drain(state)
            state.source.start()
            state.reset_format()
            state.next_cause = cause
            state.padding = False

    def stats(self, channel: Channel) -> ChannelStats:
        with self._lock:
            s = self._states[channel]
            t = s.timeline.stats
            rms = math.sqrt(s.sum_squares / s.measured) / _FULL_SCALE if s.measured else 0.0
            return ChannelStats(
                channel=channel,
                native_rate=s.source.native_rate,
                native_channels=s.source.native_channels,
                seconds=s.frames_out * FRAME_SAMPLES / SAMPLE_RATE,
                rms_dbfs=_dbfs(rms),
                peak_dbfs=_dbfs(s.peak / _FULL_SCALE),
                dropped_chunks=s.source.ring.dropped_chunks,
                corrections=t.corrections,
                inserted_ms=t.inserted * 1000 / SAMPLE_RATE,
                dropped_ms=t.dropped * 1000 / SAMPLE_RATE,
                padded_ms=t.padded * 1000 / SAMPLE_RATE,
                drift_ms=t.drift * 1000 / SAMPLE_RATE,
                gaps=tuple(t.gaps),
            )

    def _drain(self, s: _ChannelState) -> None:
        for chunk in s.source.ring.drain():
            if chunk.seq != s.next_seq:  # the ring overflowed: audio was really lost
                s.clock = SourceClock(s.source.native_rate, latency_ns=s.source.latency_ns)
                s.next_cause = s.next_cause or "dropout"
            s.next_seq = chunk.seq + 1
            if s.padding:  # resuming after silence: re-anchor on this chunk
                s.clock = SourceClock(s.source.native_rate, latency_ns=s.source.latency_ns)
                s.next_cause = s.next_cause or "silence"
                s.padding = False
            t_first = s.clock.first_sample_ns(chunk.t_callback_ns, len(chunk.data))
            pcm = s.converter.process(chunk.data)
            self._measure(s, pcm)
            placed = s.timeline.place(pcm, t_first, cause=s.next_cause)
            s.next_cause = None
            s.buffer = np.concatenate([s.buffer, placed])
            s.last_chunk_ns = chunk.t_callback_ns

    def _maybe_pad(self, s: _ChannelState, now: int) -> None:
        if not s.source.pads_silence:
            return
        last = s.last_chunk_ns if s.last_chunk_ns is not None else self._start_ns
        if now - last < SILENCE_AFTER_NS:
            return
        fill = s.timeline.pad_until(now)
        if len(fill):
            s.padding = True
            s.buffer = np.concatenate([s.buffer, fill])

    def _emit(self, channel: Channel, s: _ChannelState) -> None:
        count = len(s.buffer) // FRAME_SAMPLES
        for k in range(count):
            index = s.frames_out * FRAME_SAMPLES
            pcm = s.buffer[k * FRAME_SAMPLES : (k + 1) * FRAME_SAMPLES].copy()
            t_ns = self._start_ns + round(index * NS / SAMPLE_RATE)
            self._on_frames(Frames(channel, pcm, t_ns, index))
            s.frames_out += 1
        s.buffer = s.buffer[count * FRAME_SAMPLES :]

    @staticmethod
    def _measure(s: _ChannelState, pcm: Int16Array) -> None:
        if len(pcm):
            as_float = pcm.astype(np.float64)
            s.sum_squares += float(np.dot(as_float, as_float))
            s.measured += len(pcm)
            s.peak = max(s.peak, int(np.max(np.abs(pcm.astype(np.int32)))))
