from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import numpy as np
import pytest

from evra.audio.frames import MIC, SYSTEM, Frames
from evra.audio.pipeline import CapturePipeline
from evra.audio.ringbuffer import ChunkRing

MS = 1_000_000


@dataclass
class StubSource:
    native_rate: int = 48_000
    native_channels: int = 2
    pads_silence: bool = False
    name: str = "stub"
    latency_ns: int = 0
    ring: ChunkRing = field(default_factory=lambda: ChunkRing(200))
    overflows: int = 0
    on_start: Callable[[], None] | None = None
    on_stop: Callable[[], None] | None = None

    def start(self) -> None:
        if self.on_start:
            self.on_start()

    def stop(self) -> None:
        if self.on_stop:
            self.on_stop()

    def reopen(self) -> None:
        self.stop()
        self.start()

    def is_active(self) -> bool:
        return True


class FakeClock:
    def __init__(self) -> None:
        self.t = 0

    def __call__(self) -> int:
        return self.t


def _chunk(rate: int, channels: int, amp: float = 0.5, i: int = 0) -> np.ndarray:
    n = rate // 100
    t = (np.arange(n) + i * n) / rate
    mono = (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1)


@pytest.fixture
def rig() -> Iterator[tuple[StubSource, StubSource, FakeClock, list[Frames], CapturePipeline]]:
    mic = StubSource(native_rate=44_100, native_channels=1)
    system = StubSource(pads_silence=True)
    clock = FakeClock()
    frames: list[Frames] = []
    pipe = CapturePipeline({MIC: mic, SYSTEM: system}, frames.append, start_ns=0, now_ns=clock)
    yield mic, system, clock, frames, pipe


def _tick(rig_parts, i: int, *, system: bool = True) -> None:  # type: ignore[no-untyped-def]
    mic, sysrc, clock, _, pipe = rig_parts
    clock.t = (i + 1) * 10 * MS
    mic.ring.put(_chunk(44_100, 1, i=i), clock.t)
    if system:
        sysrc.ring.put(_chunk(48_000, 2, i=i), clock.t)
    pipe.step()


def _per_channel(frames: list[Frames], ch: int) -> list[Frames]:
    return [f for f in frames if f.channel == ch]


def test_emits_contiguous_10ms_frames_per_channel(rig) -> None:  # type: ignore[no-untyped-def]
    for i in range(100):
        _tick(rig, i)
    frames = rig[3]
    for ch in (MIC, SYSTEM):
        chan = _per_channel(frames, ch)
        assert len(chan) >= 98
        assert all(len(f.pcm) == 160 and f.pcm.dtype == np.int16 for f in chan)
        assert [f.index for f in chan] == [k * 160 for k in range(len(chan))]
        assert all(f.t_capture_ns == f.index * 62_500 for f in chan)


def test_loopback_silence_is_padded_and_resume_keeps_alignment(rig) -> None:  # type: ignore[no-untyped-def]
    for i in range(300):
        _tick(rig, i, system=not (100 <= i < 200))
        if 150 <= i < 160:  # while silent, the system channel keeps moving
            assert _per_channel(rig[3], SYSTEM)[-1].index >= (i - 20) * 160
    pipe = rig[4]
    pipe.flush()
    mic_n = len(_per_channel(rig[3], MIC))
    sys_n = len(_per_channel(rig[3], SYSTEM))
    assert abs(mic_n - sys_n) <= 3  # within 30 ms
    stats = pipe.stats(SYSTEM)
    assert stats.padded_ms >= 800
    assert all(g.cause == "silence" for g in stats.gaps)
    assert stats.dropped_ms == 0


def test_ring_overflow_counts_drops_and_records_a_dropout_gap(rig) -> None:  # type: ignore[no-untyped-def]
    _mic, system, clock, _frames, pipe = rig
    for i in range(250):  # 2.5 s without a pipeline step: the 2 s ring overflows
        clock.t = (i + 1) * 10 * MS
        system.ring.put(_chunk(48_000, 2, i=i), clock.t)
    pipe.step()
    stats = pipe.stats(SYSTEM)
    assert stats.dropped_chunks == 50
    assert stats.gaps and stats.gaps[0].cause == "dropout"


def test_swap_source_records_device_change_gap_and_new_rate(rig) -> None:  # type: ignore[no-untyped-def]
    mic, system, clock, _frames, pipe = rig
    for i in range(100):
        _tick(rig, i)

    def new_device() -> None:
        system.native_rate, system.native_channels = 44_100, 1

    system.on_start = new_device
    pipe.swap_source(SYSTEM)
    for i in range(130, 230):  # new device starts 300 ms later at 44.1 kHz mono
        clock.t = (i + 1) * 10 * MS
        mic.ring.put(_chunk(44_100, 1, i=i), clock.t)
        system.ring.put(_chunk(44_100, 1, i=i), clock.t)
        pipe.step()
    causes = [g.cause for g in pipe.stats(SYSTEM).gaps]
    assert "device_change" in causes
    assert pipe.stats(SYSTEM).native_rate == 44_100


def test_flush_zero_pads_the_last_partial_frame(rig) -> None:  # type: ignore[no-untyped-def]
    for i in range(5):
        _tick(rig, i)
    rig[4].flush()
    for ch in (MIC, SYSTEM):
        assert all(len(f.pcm) == 160 for f in _per_channel(rig[3], ch))


def test_levels_are_measured_in_dbfs(rig) -> None:  # type: ignore[no-untyped-def]
    for i in range(200):
        _tick(rig, i)
    stats = rig[4].stats(MIC)
    assert -9.6 < stats.rms_dbfs < -8.5  # 0.5-amplitude sine ≈ -9.03 dBFS
    assert -6.5 < stats.peak_dbfs < -5.5
    assert stats.seconds == pytest.approx(len(_per_channel(rig[3], MIC)) / 100)


def test_swap_handles_a_late_chunk_from_the_old_device(rig) -> None:  # type: ignore[no-untyped-def]
    mic, system, clock, _frames, pipe = rig
    for i in range(100):
        _tick(rig, i)

    def old_device_last_callback() -> None:  # PortAudio can deliver one more buffer on stop
        system.ring.put(_chunk(48_000, 2, i=100), clock.t)

    def new_device() -> None:  # 2-channel speakers -> 1-channel Bluetooth hands-free
        system.native_rate, system.native_channels = 16_000, 1

    system.on_stop = old_device_last_callback
    system.on_start = new_device
    pipe.swap_source(SYSTEM)
    for i in range(130, 230):
        clock.t = (i + 1) * 10 * MS
        mic.ring.put(_chunk(44_100, 1, i=i), clock.t)
        system.ring.put(_chunk(16_000, 1, i=i), clock.t)
        pipe.step()
    stats = pipe.stats(SYSTEM)
    assert stats.native_channels == 1
    assert [g.cause for g in stats.gaps] == ["device_change"]


def _passthrough_rig() -> tuple[StubSource, StubSource, FakeClock, list[Frames], CapturePipeline]:
    mic = StubSource(native_rate=16_000, native_channels=1)
    system = StubSource(native_rate=16_000, native_channels=1, pads_silence=True)
    clock = FakeClock()
    frames: list[Frames] = []
    pipe = CapturePipeline({MIC: mic, SYSTEM: system}, frames.append, start_ns=0, now_ns=clock)
    return mic, system, clock, frames, pipe


def _level(i: int) -> np.ndarray:
    return np.full((160, 1), (i + 1) / 1000, dtype=np.float32)  # rises chunk by chunk


def _pcm_of(frames: list[Frames], ch: int) -> np.ndarray:
    return np.concatenate([f.pcm for f in frames if f.channel == ch])


@pytest.mark.parametrize("silence_ms", [60, 80, 100])
def test_short_loopback_silence_keeps_order_and_is_not_a_dropout(silence_ms: int) -> None:
    mic, system, clock, frames, pipe = _passthrough_rig()
    quiet = range(100, 100 + silence_ms // 10)
    for i in range(300):
        clock.t = (i + 1) * 10 * MS
        mic.ring.put(_level(i), clock.t)
        if i not in quiet:
            system.ring.put(_level(i), clock.t)
        pipe.step()
    pipe.flush()
    audio = _pcm_of(frames, SYSTEM)
    heard = audio[audio != 0].astype(np.int32)
    assert np.all(np.diff(heard) >= 0)  # resumed audio never lands before earlier audio
    stats = pipe.stats(SYSTEM)
    assert all(g.cause == "silence" for g in stats.gaps)
    assert stats.dropped_ms == 0


@pytest.mark.parametrize("stall_ms", [90, 150])
def test_callback_stall_with_burst_catch_up_loses_nothing(stall_ms: int) -> None:
    mic, system, clock, frames, pipe = _passthrough_rig()
    backlog = range(100, 100 + stall_ms // 10 + 1)
    release = 101 * 10 * MS + stall_ms * MS
    for i in range(300):
        clock.t = release if i in backlog else (i + 1) * 10 * MS
        mic.ring.put(_level(i), clock.t)
        system.ring.put(_level(i), clock.t)
        if i not in backlog or i == backlog[-1]:
            pipe.step()
    pipe.flush()
    stats = pipe.stats(MIC)
    assert stats.gaps == () and stats.dropped_ms == 0 and stats.corrections == 0
    assert len(_pcm_of(frames, MIC)) == 300 * 160


def test_a_late_first_callback_needs_no_correction_later() -> None:
    mic, system, clock, _frames, pipe = _passthrough_rig()
    for i in range(300):
        clock.t = (i + 1) * 10 * MS
        late = 35 * MS if i == 0 else 0  # the first callback is often slow
        mic.ring.put(_level(i), clock.t + late)
        system.ring.put(_level(i), clock.t)
        pipe.step()
    pipe.flush()
    stats = pipe.stats(MIC)
    assert stats.corrections == 0 and stats.dropped_ms == 0
