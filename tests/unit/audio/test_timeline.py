import numpy as np

from evra.audio.clock import ChannelTimeline

MS = 1_000_000
CHUNK = 160  # 10 ms at 16 kHz


def _pcm(n: int = CHUNK, value: int = 1000) -> np.ndarray:
    return np.full(n, value, dtype=np.int16)


def test_on_time_chunks_pass_through_unchanged() -> None:
    tl = ChannelTimeline(0)
    for i in range(300):
        out = tl.place(_pcm(), i * 10 * MS)
        assert len(out) == CHUNK
    assert tl.emitted == 300 * CHUNK
    assert tl.stats.corrections == 0 and tl.stats.gaps == []
    assert tl.stats.drift == 0


def test_small_jitter_is_not_corrected() -> None:
    tl = ChannelTimeline(0)
    for i in range(500):
        jitter = ((5 if i % 2 else -5) if i else 0) * MS  # first chunk on time
        tl.place(_pcm(), i * 10 * MS + jitter)
    assert tl.stats.corrections == 0
    assert tl.emitted == 500 * CHUNK


def test_hole_of_50ms_or_more_becomes_a_gap_filled_with_silence() -> None:
    tl = ChannelTimeline(0)
    for i in range(10):
        tl.place(_pcm(), i * 10 * MS)
    out = tl.place(_pcm(), 400 * MS)  # 300 ms hole after 100 ms of audio
    assert len(out) == 4800 + CHUNK
    assert not out[:4800].any()
    [gap] = tl.stats.gaps
    assert (gap.start, gap.length, gap.cause) == (1600, 4800, "dropout")


def test_gap_cause_is_recorded() -> None:
    tl = ChannelTimeline(0)
    tl.place(_pcm(), 0)
    tl.place(_pcm(), 500 * MS, cause="device_change")
    assert tl.stats.gaps[0].cause == "device_change"


def _simulate(speed: float, minutes: int) -> tuple[ChannelTimeline, int]:
    tl = ChannelTimeline(0)
    worst = 0
    for i in range(minutes * 60 * 100):
        tl.place(_pcm(), round(i * 10 * MS / speed))
        worst = max(worst, abs(tl.stats.drift))
    return tl, worst


def test_fast_device_is_corrected_by_dropping_in_10ms_steps() -> None:
    tl, worst = _simulate(speed=1.001, minutes=60)
    assert tl.stats.corrections > 0 and tl.stats.dropped > 0
    assert worst < 480  # < 30 ms at every point of a 60-minute run
    assert tl.stats.dropped % CHUNK == 0


def test_slow_device_is_corrected_by_inserting_silence() -> None:
    tl, worst = _simulate(speed=0.999, minutes=10)
    assert tl.stats.inserted > 0 and worst < 480


def test_pad_until_keeps_the_timeline_moving() -> None:
    tl = ChannelTimeline(0)
    fill = tl.pad_until(1_000 * MS)
    assert len(fill) == 14_400 and not fill.any()  # up to now - 100 ms
    assert tl.stats.padded == 14_400
    assert len(tl.pad_until(1_050 * MS)) == 800
    assert len(tl.pad_until(1_052 * MS)) == 0  # less than one frame missing


def test_audio_from_before_the_start_is_trimmed_not_corrected_later() -> None:
    tl = ChannelTimeline(0)
    out = tl.place(_pcm(1600), -50 * MS)  # a 100 ms chunk that began 50 ms before start
    assert len(out) == 800
    for i in range(300):
        tl.place(_pcm(), 50 * MS + i * 10 * MS)
    assert tl.stats.corrections == 0 and tl.stats.dropped == 0


def test_a_late_starting_device_gets_leading_silence_not_a_gap() -> None:
    tl = ChannelTimeline(0)
    out = tl.place(_pcm(), 200 * MS)  # first audio 200 ms after start
    assert len(out) == 3200 + CHUNK and not out[:3200].any()
    assert tl.stats.gaps == [] and tl.stats.padded == 3200
