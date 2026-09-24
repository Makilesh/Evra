import time
from collections.abc import Callable

import numpy as np
import pytest

from evra.audio.frames import MIC, SYSTEM, Frames
from evra.capture.fake import FakeEvent, FakeSource
from evra.capture.session import CaptureSession
from evra.capture.sources import CaptureError


def _sine(rate: int, seconds: float, channels: int) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    mono = (0.3 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1)


def _sources(
    seconds: float = 1.0, events: tuple[FakeEvent, ...] = ()
) -> tuple[FakeSource, FakeSource]:
    mic = FakeSource(_sine(44_100, seconds, 1), 44_100, name="fake mic")
    system = FakeSource(
        _sine(48_000, seconds, 2), 48_000, name="fake out", pads_silence=True, events=events
    )
    return mic, system


def _run(
    session: CaptureSession, mic: FakeSource, system: FakeSource
) -> tuple[list[Frames], object]:
    frames: list[Frames] = []
    session.start(frames.append)
    assert mic.finished.wait(5) and system.finished.wait(5)
    time.sleep(0.05)
    return frames, session.stop()


def test_real_time_run_produces_aligned_channels_and_a_healthy_report() -> None:
    mic, system = _sources(1.0)
    frames, health = _run(CaptureSession(mic, system), mic, system)
    mic_n = sum(f.channel == MIC for f in frames)
    sys_n = sum(f.channel == SYSTEM for f in frames)
    assert mic_n >= 95 and abs(mic_n - sys_n) <= 3
    assert health.ok  # type: ignore[attr-defined]
    assert health.channels["mic"].device == "fake mic"  # type: ignore[attr-defined]
    assert health.inter_channel_drift_ms < 30  # type: ignore[attr-defined]
    assert (
        -14.5 < health.channels["system"].rms_dbfs < -12.5
    )  # 0.3 sine ≈ -13.5 dBFS  # type: ignore[attr-defined]


def test_dropout_makes_the_report_not_ok() -> None:
    mic, system = _sources(1.0, (FakeEvent("dropout", 0.3, 0.3),))
    system.pads_silence = False  # a mic-like source: a hole is a dropout, not silence
    _, health = _run(CaptureSession(mic, system), mic, system)
    gaps = health.channels["system"].gaps  # type: ignore[attr-defined]
    assert any(g["cause"] == "dropout" for g in gaps)
    assert not health.ok  # type: ignore[attr-defined]


def test_output_change_reopens_loopback_and_is_counted() -> None:
    mic, system = _sources(1.0)
    callbacks: list[Callable[[str | None], None]] = []

    class ManualWatcher:
        def __init__(self, on_change: Callable[[str | None], None]) -> None:
            callbacks.append(on_change)

        def start(self) -> None: ...

        def stop(self) -> None: ...

    session = CaptureSession(mic, system, watcher_factory=ManualWatcher)
    frames: list[Frames] = []
    session.start(frames.append)
    time.sleep(0.2)
    callbacks[0]("new-device")
    assert mic.finished.wait(5) and system.finished.wait(5)
    health = session.stop()
    assert health.device_changes == 1


def test_silent_mic_produces_a_hint() -> None:
    mic = FakeSource(np.zeros((44_100, 1), dtype=np.float32), 44_100, name="muted")
    _, system = _sources(1.0)
    _, health = _run(CaptureSession(mic, system), mic, system)
    assert any("icrophone" in h for h in health.hints)  # type: ignore[attr-defined]


def test_start_failure_of_system_stops_the_mic() -> None:
    mic, _ = _sources(0.5)

    class Broken(FakeSource):
        def start(self) -> None:
            raise CaptureError("no output", "plug something in")

    broken = Broken(np.zeros((480, 2), dtype=np.float32), 48_000)
    session = CaptureSession(mic, broken)
    with pytest.raises(CaptureError):
        session.start(lambda f: None)
    assert mic._thread is None  # mic was stopped again


def test_frame_consumer_failure_stops_capture_and_is_reported() -> None:
    mic, system = _sources(1.0)
    session = CaptureSession(mic, system)

    def broken_writer(frames: Frames) -> None:
        raise OSError("disk full")

    session.start(broken_writer)
    time.sleep(0.3)
    health = session.stop()
    assert not health.ok
    assert any("OSError" in h for h in health.hints)


def test_clean_start_needs_no_drift_corrections() -> None:
    mic, system = _sources(2.5)

    class SlowStart(FakeSource):
        def start(self) -> None:
            time.sleep(0.2)  # a real loopback open can take this long
            super().start()

    slow = SlowStart(system.audio, 48_000, name="slow out", pads_silence=True)
    _frames, health = _run(CaptureSession(mic, slow), mic, slow)
    for ch in ("mic", "system"):
        assert health.channels[ch].corrections == 0  # type: ignore[attr-defined]
        assert health.channels[ch].dropped_ms == 0  # type: ignore[attr-defined]
        assert health.channels[ch].gaps == []  # type: ignore[attr-defined]


def test_start_failure_with_os_error_still_stops_the_mic() -> None:
    mic, _ = _sources(0.5)

    class Broken(FakeSource):
        def start(self) -> None:
            raise OSError("device in use")

    session = CaptureSession(mic, Broken(np.zeros((480, 2), dtype=np.float32), 48_000))
    with pytest.raises(OSError):
        session.start(lambda f: None)
    assert mic._thread is None


def test_failed_reopen_does_not_escape_the_watcher_callback() -> None:
    mic, system = _sources(1.0)
    callbacks: list[Callable[[str | None], None]] = []

    class ManualWatcher:
        def __init__(self, on_change: Callable[[str | None], None]) -> None:
            callbacks.append(on_change)

        def start(self) -> None: ...

        def stop(self) -> None: ...

    session = CaptureSession(mic, system, watcher_factory=ManualWatcher)
    session.start(lambda f: None)
    time.sleep(0.1)

    def broken_start() -> None:
        raise OSError("new device not ready")

    system.start = broken_start  # type: ignore[method-assign]
    callbacks[0]("new-device")  # must not raise
    assert mic.finished.wait(5)
    session.stop()
