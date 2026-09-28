"""Speech segments from one channel's timeline audio (BUILD.md §5.4, Silero VAD via sherpa-onnx)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from evra.audio.convert import float_to_int16
from evra.audio.frames import SAMPLE_RATE, Float32Array, Frames, Int16Array

VAD_WINDOW = 512  # Silero's window at 16 kHz
PRE_ROLL_MS = 300


@dataclass(frozen=True)
class SpeechSegment:
    channel: int
    start_index: int  # timeline sample index of pcm[0]
    pcm: Int16Array

    @property
    def start_ms(self) -> int:
        return self.start_index * 1000 // SAMPLE_RATE

    @property
    def end_ms(self) -> int:
        return (self.start_index + len(self.pcm)) * 1000 // SAMPLE_RATE


class VadBackend(Protocol):
    def accept_waveform(self, samples: Float32Array) -> None: ...

    def flush(self) -> None: ...

    def empty(self) -> bool: ...

    @property
    def front(self) -> Any: ...  # has .start (sample index) and .samples (float32)

    def pop(self) -> None: ...


def silero_vad(model_path: Path) -> VadBackend:
    import sherpa_onnx

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(model_path)
    config.silero_vad.threshold = 0.5
    config.silero_vad.min_speech_duration = 0.25
    config.silero_vad.min_silence_duration = 0.4
    config.silero_vad.max_speech_duration = 20.0
    config.silero_vad.window_size = VAD_WINDOW
    config.sample_rate = SAMPLE_RATE
    config.num_threads = 1
    vad: VadBackend = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=60)
    return vad


class SpeechSegmenter:
    """Feeds one channel to the VAD and returns closed speech segments, with pre-roll.

    Frames arrive contiguous from the pipeline, so the VAD's sample count maps straight onto
    the meeting timeline (offset by the channel's first frame index).
    """

    def __init__(
        self,
        channel: int,
        vad: VadBackend,
        *,
        pre_roll_ms: int = PRE_ROLL_MS,
        history_s: float = 30.0,
    ) -> None:
        self._channel = channel
        self._vad = vad
        self._pre_roll = pre_roll_ms * SAMPLE_RATE // 1000
        self._ring = np.zeros(int(history_s * SAMPLE_RATE), dtype=np.int16)
        self._written = 0  # samples appended to the history (== samples fed to the VAD)
        self._origin: int | None = None  # timeline index of the first sample
        self._pending: Float32Array = np.zeros(0, dtype=np.float32)

    def accept(self, frames: Frames) -> list[SpeechSegment]:
        if self._origin is None:
            self._origin = frames.index
        self._remember(frames.pcm)
        self._pending = np.concatenate([self._pending, frames.pcm.astype(np.float32) / 32768.0])
        while len(self._pending) >= VAD_WINDOW:
            self._vad.accept_waveform(self._pending[:VAD_WINDOW])
            self._pending = self._pending[VAD_WINDOW:]
        return self._collect()

    def flush(self) -> list[SpeechSegment]:
        if len(self._pending):
            self._vad.accept_waveform(self._pending)
            self._pending = np.zeros(0, dtype=np.float32)
        self._vad.flush()
        return self._collect()

    def _remember(self, pcm: Int16Array) -> None:
        size = len(self._ring)
        for start in range(0, len(pcm), size):
            part = pcm[start : start + size]
            at = self._written % size
            first = min(len(part), size - at)
            self._ring[at : at + first] = part[:first]
            self._ring[: len(part) - first] = part[first:]
            self._written += len(part)

    def _history(self, first: int, last: int) -> Int16Array:
        """Samples [first, last) counted from the channel start, if still remembered."""
        first = max(first, self._written - len(self._ring), 0)
        if last <= first:
            return np.zeros(0, dtype=np.int16)
        idx = np.arange(first, last) % len(self._ring)
        return self._ring[idx].copy()

    def _collect(self) -> list[SpeechSegment]:
        out: list[SpeechSegment] = []
        origin = self._origin or 0
        while not self._vad.empty():
            seg = self._vad.front
            start = int(seg.start)
            speech = float_to_int16(np.asarray(seg.samples, dtype=np.float32))
            self._vad.pop()
            pre = self._history(start - self._pre_roll, start)
            begin = start - len(pre)
            out.append(SpeechSegment(self._channel, origin + begin, np.concatenate([pre, speech])))
        return out
