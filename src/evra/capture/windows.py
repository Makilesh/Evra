"""System-output capture on Windows: WASAPI loopback (PyAudioWPatch) and default-device watch.

PortAudio's device list is fixed once initialised, so a new default output is only visible
after re-initialising PyAudio (reopen). The Windows default endpoint id comes from the
Core Audio API via pycaw (D25).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from evra.audio.ringbuffer import ChunkRing
from evra.capture.sources import NO_OUTPUT_HINT, LoopbackUnavailableError


def _pyaudio() -> Any:
    import pyaudiowpatch

    return pyaudiowpatch


class LoopbackSource:
    pads_silence = True  # WASAPI loopback may deliver nothing while nothing plays

    def __init__(
        self, *, backend: Any = None, now_ns: Callable[[], int] = time.monotonic_ns
    ) -> None:
        self._pam = backend or _pyaudio()
        self._now = now_ns
        self.ring = ChunkRing.for_duration(2.0, 0.01)
        self.name = ""
        self.native_rate = 0
        self.native_channels = 0
        self.latency_ns = 0
        self._pa: Any = None
        self._stream: Any = None
        self._cb_channels = 1

    def start(self) -> None:
        pa = self._pam.PyAudio()
        try:
            loop = pa.get_default_wasapi_loopback()
        except (LookupError, OSError, ValueError) as exc:
            pa.terminate()
            raise LoopbackUnavailableError(
                "no output device to capture from", NO_OUTPUT_HINT
            ) from exc
        rate = int(loop["defaultSampleRate"])
        channels = int(loop["maxInputChannels"])
        self._cb_channels = channels
        stream = pa.open(
            format=self._pam.paFloat32,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=int(loop["index"]),
            frames_per_buffer=rate // 100,
            stream_callback=self._callback,
        )
        self._pa, self._stream = pa, stream
        self.name = str(loop["name"])
        self.native_rate, self.native_channels = rate, channels
        self.latency_ns = int(float(stream.get_input_latency()) * 1e9)

    def _callback(
        self, in_data: bytes, frame_count: int, time_info: Any, status: int
    ) -> tuple[None, int]:
        data = np.frombuffer(in_data, dtype=np.float32).reshape(-1, self._cb_channels).copy()
        self.ring.put(data, self._now())
        return (None, self._pam.paContinue)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

    def reopen(self) -> None:
        self.stop()
        self.start()


def default_output_id() -> str | None:
    """Id of the current Windows default output endpoint, or None if there is none."""
    import comtypes
    from pycaw.pycaw import AudioUtilities

    comtypes.CoInitialize()
    try:
        return str(AudioUtilities.GetSpeakers().id)
    except Exception:  # no output endpoint, or a COM failure: treat as "none"
        return None
    finally:
        comtypes.CoUninitialize()


class DefaultOutputWatcher:
    """Polls the default output device every `interval_s` and reports changes (§5.1)."""

    def __init__(
        self,
        on_change: Callable[[str | None], None],
        *,
        get_id: Callable[[], str | None] = default_output_id,
        interval_s: float = 2.0,
    ) -> None:
        self._on_change = on_change
        self._get_id = get_id
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: str | None = None

    def start(self) -> None:
        self._last = self._get_id()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="output-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            current = self._get_id()
            if current != self._last:
                self._last = current
                self._on_change(current)
