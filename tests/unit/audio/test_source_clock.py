import random

import pytest

from evra.audio.clock import SourceClock

RATE = 48_000
FR = 480  # 10 ms
MS = 1_000_000


def _times(clock: SourceClock, callbacks: list[int], frames: int = FR) -> dict[int, int]:
    """Push every callback, flush, and return each chunk's decided first-sample time."""
    out: dict[int, int] = {}
    for key, callback in enumerate(callbacks):
        for timed in clock.push(key, callback, frames):
            out[timed.key] = timed.t_first_ns
    for timed in clock.flush():
        out[timed.key] = timed.t_first_ns
    return out


def test_steady_callbacks_give_exact_times() -> None:
    times = _times(SourceClock(RATE), [(i + 1) * 10 * MS for i in range(50)])
    assert all(times[i] == i * 10 * MS for i in range(50))


def test_every_chunk_is_released_in_order() -> None:
    clock = SourceClock(RATE)
    released: list[int] = []
    for i in range(300):
        late = 200 * MS if 100 <= i < 120 else 0
        released += [t.key for t in clock.push(i, (i + 1) * 10 * MS + late, FR)]
    released += [t.key for t in clock.flush()]
    assert released == list(range(300))


def test_jittery_callbacks_stay_within_2ms() -> None:
    rng = random.Random(7)
    callbacks = [int((i + 1) * 10 * MS + rng.uniform(0, 30) * MS) for i in range(1_000)]
    times = _times(SourceClock(RATE), callbacks)
    assert all(abs(times[i] - i * 10 * MS) < 2 * MS for i in range(50, 1_000))


def test_bursty_delivery_is_smoothed() -> None:
    callbacks = [((i // 5) + 1) * 50 * MS for i in range(500)]  # 5 chunks together every 50 ms
    times = _times(SourceClock(RATE), callbacks)
    assert all(abs(times[i] - i * 10 * MS) <= 1 * MS for i in range(5, 500))


@pytest.mark.parametrize("stall_ms", [90, 150, 300])
def test_stall_then_burst_catch_up_is_not_a_jump(stall_ms: int) -> None:
    release = 101 * 10 * MS + stall_ms * MS  # the backlog arrives all at once
    backlog = stall_ms // 10 + 1
    callbacks = [release if 100 <= i < 100 + backlog else (i + 1) * 10 * MS for i in range(400)]
    times = _times(SourceClock(RATE), callbacks)
    assert all(abs(times[i] - i * 10 * MS) <= 1 * MS for i in range(400))


def test_persistent_jump_places_resumed_audio_at_its_true_time() -> None:
    stall = 2_000 * MS  # device delivered nothing for 2 s (samples really missing)
    clock = SourceClock(RATE)
    callbacks = [(i + 1) * 10 * MS + (stall if i >= 100 else 0) for i in range(200)]
    decided = []
    for key, callback in enumerate(callbacks):
        decided += clock.push(key, callback, FR)
    by_key = {t.key: t for t in decided}
    assert all(abs(by_key[i].t_first_ns - (i * 10 * MS + stall)) <= 1 * MS for i in range(100, 200))
    assert by_key[100].jumped and not any(by_key[i].jumped for i in range(101, 200))


def test_single_late_callback_is_not_a_jump() -> None:
    callbacks = [(i + 1) * 10 * MS + (200 * MS if i == 100 else 0) for i in range(150)]
    times = _times(SourceClock(RATE), callbacks)
    assert all(abs(times[i] - i * 10 * MS) <= 1 * MS for i in range(150))


def test_follows_a_fast_device_clock() -> None:
    callbacks = [round((i + 1) * 10 * MS / 1.001) for i in range(10_000)]
    times = _times(SourceClock(RATE), callbacks)
    assert all(abs(times[i] - i * 10 * MS / 1.001) < 2 * MS for i in range(10_000))


def test_follows_a_slow_device_clock() -> None:
    callbacks = [round((i + 1) * 10 * MS / 0.999) for i in range(10_000)]
    times = _times(SourceClock(RATE), callbacks)
    assert all(abs(times[i] - i * 10 * MS / 0.999) < 2 * MS for i in range(10_000))


def test_latency_is_subtracted() -> None:
    assert _times(SourceClock(RATE, latency_ns=20 * MS), [30 * MS])[0] == 0
