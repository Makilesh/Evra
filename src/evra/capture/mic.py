"""Microphone capture with sounddevice (BUILD.md §5.1)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from evra.audio.ringbuffer import ChunkRing
from evra.capture.sources import MIC_PRIVACY_HINT, MicUnavailableError


def _sounddevice() -> Any:
    import sounddevice

    return sounddevice


def list_input_devices(backend: Any = None) -> list[dict[str, object]]:
    sd = backend or _sounddevice()
    return [
        {"index": i, "name": d["name"], "rate": d["default_samplerate"]}
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


class MicSource:
    pads_silence = False

    def __init__(
        self,
        device: int | str | None = None,
        *,
        backend: Any = None,
        now_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._sd = backend or _sounddevice()
        try:
            info = self._sd.query_devices(device, kind="input")
        except (ValueError, self._sd.PortAudioError) as exc:
            raise MicUnavailableError(f"microphone {device!r} not found", MIC_PRIVACY_HINT) from exc
        self._device = device
        self._now = now_ns
        self.name = str(info["name"])
        self.native_rate = int(info["default_samplerate"])
        self.native_channels = 1
        self.latency_ns = 0
        self.ring = ChunkRing.for_duration(2.0, 0.01)
        self.overflows = 0
        self._stream: Any = None

    def _callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        if status.input_overflow:
            self.overflows += 1
        self.ring.put(indata.copy(), self._now())

    def start(self) -> None:
        try:
            stream = self._sd.InputStream(
                device=self._device,
                samplerate=self.native_rate,
                channels=1,
                dtype="float32",
                blocksize=self.native_rate // 100,
                callback=self._callback,
            )
            stream.start()
        except self._sd.PortAudioError as exc:
            raise MicUnavailableError(
                f"could not open microphone {self.name!r}", MIC_PRIVACY_HINT
            ) from exc
        self._stream = stream
        self.latency_ns = int(float(stream.latency) * 1e9)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def is_active(self) -> bool:
        return self._stream is not None and bool(self._stream.active)

    def reopen(self) -> None:
        self.stop()
        self.start()
