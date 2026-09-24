import threading
from typing import Any

import numpy as np
import pytest

from evra.capture.sources import NO_OUTPUT_HINT, LoopbackUnavailableError
from evra.capture.windows import DefaultOutputWatcher, LoopbackSource


class FakeStream:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False

    def get_input_latency(self) -> float:
        return 0.01

    def stop_stream(self) -> None: ...

    def close(self) -> None:
        self.closed = True


class FakePyAudio:
    def __init__(self, module: "FakePaModule") -> None:
        self._m = module
        module.instances += 1

    def get_default_wasapi_loopback(self) -> dict[str, Any]:
        if self._m.no_device:
            raise LookupError("no loopback device")
        return {
            "index": 7,
            "name": f"Speakers {self._m.instances} [Loopback]",
            "defaultSampleRate": 48000.0,
            "maxInputChannels": 2,
        }

    def open(self, **kwargs: Any) -> FakeStream:
        if self._m.open_error:
            raise OSError(-9996, "Invalid device")
        self._m.stream = FakeStream(**kwargs)
        return self._m.stream

    def terminate(self) -> None:
        self._m.terminated += 1


class FakePaModule:
    paFloat32 = 1
    paContinue = 0

    def __init__(self, no_device: bool = False, open_error: bool = False) -> None:
        self.no_device = no_device
        self.open_error = open_error
        self.instances = 0
        self.terminated = 0
        self.stream: FakeStream | None = None

    def PyAudio(self) -> FakePyAudio:
        return FakePyAudio(self)


def test_opens_default_loopback_at_native_format() -> None:
    pa = FakePaModule()
    src = LoopbackSource(backend=pa, now_ns=lambda: 5)
    src.start()
    kw = pa.stream.kwargs  # type: ignore[union-attr]
    assert (kw["rate"], kw["channels"], kw["frames_per_buffer"], kw["input_device_index"]) == (
        48000,
        2,
        480,
        7,
    )
    assert (src.native_rate, src.native_channels, src.latency_ns) == (48000, 2, 10_000_000)
    assert src.pads_silence is True


def test_callback_deinterleaves_float32() -> None:
    pa = FakePaModule()
    src = LoopbackSource(backend=pa, now_ns=lambda: 9)
    src.start()
    frames = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    result = pa.stream.kwargs["stream_callback"](frames.tobytes(), 2, {}, 0)  # type: ignore[union-attr]
    assert result == (None, 0)
    [chunk] = src.ring.drain()
    np.testing.assert_array_equal(chunk.data, frames)


def test_reopen_reinitialises_portaudio_to_see_the_new_default() -> None:
    pa = FakePaModule()
    src = LoopbackSource(backend=pa)
    src.start()
    src.reopen()
    assert pa.terminated == 1 and pa.instances == 2
    assert src.name == "Speakers 2 [Loopback]"


def test_no_output_device_is_a_clear_error() -> None:
    with pytest.raises(LoopbackUnavailableError) as exc:
        LoopbackSource(backend=FakePaModule(no_device=True)).start()
    assert exc.value.hint == NO_OUTPUT_HINT


def test_watcher_reports_changes_only() -> None:
    ids = iter(["A", "A", "B", "B", "C"])
    seen: list[str | None] = []
    got_two = threading.Event()

    def on_change(new: str | None) -> None:
        seen.append(new)
        if len(seen) == 2:
            got_two.set()

    watcher = DefaultOutputWatcher(on_change, get_id=lambda: next(ids, "C"), interval_s=0.001)
    watcher.start()
    assert got_two.wait(2)
    watcher.stop()
    assert seen[:2] == ["B", "C"]


def test_open_failure_is_a_clear_error_and_releases_portaudio() -> None:
    pa = FakePaModule(open_error=True)
    with pytest.raises(LoopbackUnavailableError):
        LoopbackSource(backend=pa).start()
    assert pa.terminated == 1


def test_stop_survives_a_device_that_already_vanished() -> None:
    pa = FakePaModule()
    src = LoopbackSource(backend=pa)
    src.start()

    def gone() -> None:
        raise OSError(-9999, "Unanticipated host error")

    pa.stream.stop_stream = gone  # type: ignore[union-attr, method-assign]
    src.stop()
    assert pa.terminated == 1


def test_watcher_keeps_polling_after_errors() -> None:
    calls = {"n": 0}

    def flaky_id() -> str | None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("COM hiccup")
        return "A" if calls["n"] < 4 else "B"

    seen: list[str | None] = []
    got = threading.Event()

    def on_change(new: str | None) -> None:
        seen.append(new)
        if new == "B":
            got.set()
        raise RuntimeError("handler bug")  # must not kill the watcher either

    watcher = DefaultOutputWatcher(on_change, get_id=flaky_id, interval_s=0.001)
    watcher.start()
    assert got.wait(2)
    watcher.stop()


def test_loopback_counts_input_overflow_status() -> None:
    pa = FakePaModule()
    src = LoopbackSource(backend=pa)
    src.start()
    frames = np.zeros((2, 2), dtype=np.float32)
    pa.stream.kwargs["stream_callback"](frames.tobytes(), 2, {}, 2)  # type: ignore[union-attr]
    assert src.overflows == 1
