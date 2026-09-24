"""Downmix + resample native capture audio to the 16 kHz mono int16 timeline (BUILD.md §5.1).

libsamplerate keeps filter state between calls, so a stream converted chunk by chunk has
no seams (D24).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import samplerate

from evra.audio.frames import SAMPLE_RATE, Float32Array, Int16Array


def float_to_int16(samples: npt.ArrayLike) -> Int16Array:
    result: Int16Array = np.round(np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    return result


class ToMono16k:
    def __init__(self, native_rate: int, channels: int, converter: str = "sinc_fastest") -> None:
        if native_rate <= 0 or channels <= 0:
            raise ValueError(f"bad audio format: {native_rate} Hz, {channels} channels")
        self.native_rate = native_rate
        self.channels = channels
        self._ratio = SAMPLE_RATE / native_rate
        self._resampler = (
            None if native_rate == SAMPLE_RATE else samplerate.Resampler(converter, channels=1)
        )

    def process(self, chunk: Float32Array) -> Int16Array:
        data = np.asarray(chunk, dtype=np.float32)
        if data.ndim == 2:
            if data.shape[1] != self.channels:
                raise ValueError(f"expected {self.channels} channels, got {data.shape[1]}")
            mono = data.mean(axis=1, dtype=np.float32) if self.channels > 1 else data[:, 0]
        else:
            mono = data
        if len(mono) == 0:
            return np.zeros(0, dtype=np.int16)
        if self._resampler is not None:
            mono = self._resampler.process(np.ascontiguousarray(mono), self._ratio)
        return float_to_int16(mono)
