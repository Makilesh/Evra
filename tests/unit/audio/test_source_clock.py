import random

from evra.audio.clock import SourceClock

RATE = 48_000
FR = 480  # 10 ms
MS = 1_000_000


def test_steady_callbacks_give_exact_times() -> None:
    clock = SourceClock(RATE)
    for i in range(50):
        assert clock.first_sample_ns((i + 1) * 10 * MS, FR) == i * 10 * MS


def test_jittery_callbacks_stay_within_2ms() -> None:
    rng = random.Random(7)
    clock = SourceClock(RATE)
    for i in range(1_000):
        late = rng.uniform(0, 30) * MS
        t = clock.first_sample_ns(int((i + 1) * 10 * MS + late), FR)
        if i >= 50:
            assert abs(t - i * 10 * MS) < 2 * MS


def test_bursty_delivery_is_smoothed() -> None:
    clock = SourceClock(RATE)
    for i in range(500):
        callback = ((i // 5) + 1) * 50 * MS  # 5 chunks arrive together every 50 ms
        t = clock.first_sample_ns(callback, FR)
        if i >= 5:
            assert abs(t - i * 10 * MS) <= 1 * MS


def test_persistent_jump_moves_the_anchor() -> None:
    clock = SourceClock(RATE)
    for i in range(100):
        clock.first_sample_ns((i + 1) * 10 * MS, FR)
    stall = 2_000 * MS
    times = [clock.first_sample_ns((i + 1) * 10 * MS + stall, FR) for i in range(100, 110)]
    for i, t in zip(range(102, 110), times[2:], strict=True):
        assert abs(t - (i * 10 * MS + stall)) <= 1 * MS


def test_single_late_callback_is_not_a_jump() -> None:
    clock = SourceClock(RATE)
    for i in range(100):
        clock.first_sample_ns((i + 1) * 10 * MS, FR)
    clock.first_sample_ns(101 * 10 * MS + 200 * MS, FR)
    for i in range(101, 150):
        assert abs(clock.first_sample_ns((i + 1) * 10 * MS, FR) - i * 10 * MS) <= 1 * MS


def test_follows_a_fast_device_clock() -> None:
    clock = SourceClock(RATE)
    for i in range(10_000):
        wall = (i + 1) * 10 * MS / 1.001
        t = clock.first_sample_ns(round(wall), FR)
        assert abs(t - i * 10 * MS / 1.001) < 2 * MS


def test_follows_a_slow_device_clock() -> None:
    clock = SourceClock(RATE)
    for i in range(10_000):
        wall = (i + 1) * 10 * MS / 0.999
        t = clock.first_sample_ns(round(wall), FR)
        assert abs(t - i * 10 * MS / 0.999) < 2 * MS


def test_latency_is_subtracted() -> None:
    clock = SourceClock(RATE, latency_ns=20 * MS)
    assert clock.first_sample_ns(30 * MS, FR) == 0
