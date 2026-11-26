import threading

import structlog

from evra.capture.awake import KeepAwake

HOLD = 0x80000001  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: keep the system (not the screen) on
CLEAR = 0x80000000  # ES_CONTINUOUS alone: back to normal


class FakePower:
    """Stands in for SetThreadExecutionState: records each request and the thread that made
    it, because Windows ties a request to that thread."""

    def __init__(self, answer: int = CLEAR) -> None:
        self.answer = answer  # the previous state; 0 means the request failed
        self.calls: list[tuple[int, int]] = []

    def __call__(self, flags: int) -> int:
        self.calls.append((flags, threading.get_ident()))
        return self.answer

    def flags(self) -> list[int]:
        return [flags for flags, _ in self.calls]


def test_the_pc_is_held_awake_until_released() -> None:
    power = FakePower()
    awake = KeepAwake(power)
    awake.start()
    assert power.flags() == [HOLD]
    awake.stop()
    assert power.flags() == [HOLD, CLEAR]
    (_, held_by), (_, released_by) = power.calls
    assert held_by == released_by  # only the thread that made a request can clear it


def test_the_hold_outlives_the_thread_that_asked_for_it() -> None:
    # Bridge calls run on short-lived threads, and Windows drops a thread's request when the
    # thread ends: the hold has to live on a thread of its own.
    power = FakePower()
    awake = KeepAwake(power)
    asker = threading.Thread(target=awake.start)
    asker.start()
    asker.join()
    [(flags, held_by)] = power.calls
    assert flags == HOLD and held_by != asker.ident
    assert any(t.ident == held_by and t.is_alive() for t in threading.enumerate())
    awake.stop()
    assert power.flags() == [HOLD, CLEAR]


def test_holding_twice_asks_once_and_releasing_twice_is_harmless() -> None:
    power = FakePower()
    awake = KeepAwake(power)
    awake.start()
    awake.start()
    awake.stop()
    awake.stop()
    assert power.flags() == [HOLD, CLEAR]


def test_a_refused_hold_is_logged_and_nothing_else_changes() -> None:
    power = FakePower(answer=0)
    awake = KeepAwake(power)
    with structlog.testing.capture_logs() as logs:
        awake.start()
        awake.stop()
    assert any(e["event"] == "keep_awake_refused" for e in logs)
    assert power.flags() == [HOLD, CLEAR]


def test_without_an_os_request_nothing_is_held() -> None:
    awake = KeepAwake(None)  # not Windows
    awake.start()
    assert not any(t.name == "keep-awake" for t in threading.enumerate())
    awake.stop()
