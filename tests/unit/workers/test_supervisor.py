import pytest

from evra.workers.protocol import WorkerCrashed, WorkerError
from evra.workers.supervisor import Worker

FACTORY = "tests.unit.workers.fake_handlers:echo"


@pytest.fixture
def worker():  # type: ignore[no-untyped-def]
    w = Worker("test", FACTORY, {"threads": 2})
    yield w
    w.stop()


def test_starts_lazily_and_answers(worker) -> None:  # type: ignore[no-untyped-def]
    assert not worker.alive
    assert worker.call("echo", {"x": [1, 2]}, timeout=30) == {"x": [1, 2]}
    assert worker.alive
    assert worker.call("config", None, timeout=5) == {"threads": 2}


def test_errors_cross_as_type_names_only(worker) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(WorkerError) as exc:
        worker.call("boom", None, timeout=30)
    assert exc.value.error_type == "ValueError"
    assert "secret" not in str(exc.value)


def test_crash_fails_pending_and_next_call_restarts(worker) -> None:  # type: ignore[no-untyped-def]
    first_pid = worker.call("pid", None, timeout=30)
    with pytest.raises(WorkerCrashed):
        worker.call("die", None, timeout=30)
    assert worker.call("pid", None, timeout=30) != first_pid


def test_idle_worker_is_stopped_and_restarted_on_demand() -> None:
    now = [0.0]
    w = Worker("idle", FACTORY, idle_timeout_s=10, clock=lambda: now[0])
    try:
        w.call("echo", 1, timeout=30)
        assert not w.stop_if_idle()
        now[0] = 11
        assert w.stop_if_idle() and not w.alive
        assert w.call("echo", 2, timeout=30) == 2
    finally:
        w.stop()


def test_stop_is_clean_and_idempotent(worker) -> None:  # type: ignore[no-untyped-def]
    worker.call("echo", 1, timeout=30)
    worker.stop()
    worker.stop()
    assert not worker.alive


BIG = b"x" * 65_536  # larger than a Windows pipe buffer: send() blocks if the child stops reading


def test_hung_request_times_out_and_the_worker_is_replaced(worker) -> None:  # type: ignore[no-untyped-def]
    import time

    first_pid = worker.call("pid", None, timeout=30)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        worker.call("sleep", {"s": 60, "blob": BIG}, timeout=2)
    assert time.monotonic() - started < 10
    with pytest.raises(TimeoutError):  # a second big request must not block forever either
        worker.call("sleep", {"s": 60, "blob": BIG}, timeout=2)
    assert worker.call("pid", None, timeout=30) != first_pid


def test_stop_returns_promptly_while_a_request_hangs(worker) -> None:  # type: ignore[no-untyped-def]
    import time

    worker.call("pid", None, timeout=30)
    for _ in range(3):
        worker.submit("sleep", {"s": 60, "blob": BIG})
    started = time.monotonic()
    worker.stop()
    assert time.monotonic() - started < 12 and not worker.alive


def test_worker_ignores_ctrl_c(worker) -> None:  # type: ignore[no-untyped-def]
    assert worker.call("sigint", None, timeout=30) is True  # the app owns the worker's lifetime
