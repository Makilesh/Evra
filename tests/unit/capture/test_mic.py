from typing import Any

import numpy as np
import pytest

from evra.capture.mic import MicSource
from evra.capture.sources import MIC_PRIVACY_HINT, MicUnavailableError


class FakePortAudioError(Exception):
    pass


class FakeFlags:
    def __init__(self, overflow: bool = False) -> None:
        self.input_overflow = overflow


class FakeStream:
    def __init__(self, fail: bool, **kwargs: Any) -> None:
        if fail:
            raise FakePortAudioError("Error opening InputStream: Unanticipated host error")
        self.kwargs = kwargs
        self.latency = 0.02
        self.started = self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.closed = True


class FakeSd:
    PortAudioError = FakePortAudioError

    def __init__(self, *, fail_open: bool = False, missing: bool = False) -> None:
        self.fail_open = fail_open
        self.missing = missing
        self.stream: FakeStream | None = None

    def query_devices(self, device: Any = None, kind: str | None = None) -> Any:
        if self.missing:
            raise ValueError("No input device matching 'nope'")
        return {"name": "Test Mic", "default_samplerate": 44100.0, "max_input_channels": 1}

    def InputStream(self, **kwargs: Any) -> FakeStream:
        self.stream = FakeStream(self.fail_open, **kwargs)
        return self.stream


def test_opens_at_native_rate_with_10ms_blocks() -> None:
    sd = FakeSd()
    mic = MicSource(backend=sd, now_ns=lambda: 123)
    mic.start()
    assert sd.stream is not None and sd.stream.started
    kw = sd.stream.kwargs
    assert (kw["samplerate"], kw["channels"], kw["dtype"], kw["blocksize"]) == (
        44100,
        1,
        "float32",
        441,
    )
    assert mic.latency_ns == 20_000_000 and mic.name == "Test Mic"
    mic.stop()
    assert sd.stream.closed


def test_callback_copies_data_and_counts_overflows() -> None:
    sd = FakeSd()
    mic = MicSource(backend=sd, now_ns=lambda: 7)
    mic.start()
    buf = np.ones((441, 1), dtype=np.float32)
    sd.stream.kwargs["callback"](buf, 441, None, FakeFlags(overflow=True))  # type: ignore[union-attr]
    buf[:] = 0  # sounddevice reuses its buffer
    [chunk] = mic.ring.drain()
    assert chunk.data.all() and chunk.t_callback_ns == 7
    assert mic.overflows == 1


def test_start_failure_maps_to_mic_unavailable_with_privacy_hint() -> None:
    mic = MicSource(backend=FakeSd(fail_open=True))
    with pytest.raises(MicUnavailableError) as exc:
        mic.start()
    assert exc.value.hint == MIC_PRIVACY_HINT


def test_unknown_device_is_a_clear_error() -> None:
    with pytest.raises(MicUnavailableError, match="not found"):
        MicSource("nope", backend=FakeSd(missing=True))


def test_is_active_follows_the_stream() -> None:
    sd = FakeSd()
    mic = MicSource(backend=sd)
    assert not mic.is_active()
    mic.start()
    sd.stream.active = True  # type: ignore[union-attr]
    assert mic.is_active()
    sd.stream.active = False  # type: ignore[union-attr]
    assert not mic.is_active()
