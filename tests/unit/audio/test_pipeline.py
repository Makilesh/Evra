from collections.abc import Iterator
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

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def reopen(self) -> None: ...


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

    def reopen() -> None:
        system.native_rate, system.native_channels = 44_100, 1

    pipe.swap_source(SYSTEM, reopen)
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
