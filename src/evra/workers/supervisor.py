"""A model worker process: started on first use, stopped when idle, restarted after a crash
or a hang (BUILD.md §4.2).

Each running child is a *generation* with its own pipe, pending requests, reader thread and
sender thread. Sends never happen under the state lock: a Windows pipe blocks once its buffer
fills, so a hung child must never be able to freeze callers or `stop()`. A request that misses
its deadline kills the whole generation; the next request starts a fresh one. (Periodic
heartbeats are deferred: per-request deadlines are the liveness check for now.)
"""

from __future__ import annotations

import contextlib
import itertools
import multiprocessing
import queue
import sys
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any

if sys.platform == "win32":  # Pipe() gives a PipeConnection on Windows
    from multiprocessing.connection import PipeConnection as _Pipe
else:
    from multiprocessing.connection import Connection as _Pipe

from evra.workers.protocol import SHUTDOWN, Request, WorkerCrashed, WorkerError, worker_main

_STOP_SENDER = object()


class _Generation:
    """One child process and everything that talks to it."""

    def __init__(self, name: str, factory: str, config: dict[str, Any]) -> None:
        ctx = multiprocessing.get_context("spawn")
        parent, child = ctx.Pipe()
        self.name = name
        self.proc: BaseProcess = ctx.Process(
            target=worker_main, args=(child, factory, config), name=f"evra-{name}", daemon=True
        )
        self.proc.start()
        child.close()
        self.conn: Connection | _Pipe = parent
        self.pending: dict[int, Future[Any]] = {}
        self.lock = threading.Lock()
        self.outbox: queue.Queue[object] = queue.Queue()
        self.dead = False
        self.reader = threading.Thread(target=self._read, name=f"{name}-reader", daemon=True)
        self.sender = threading.Thread(target=self._send, name=f"{name}-sender", daemon=True)
        self.reader.start()
        self.sender.start()

    def enqueue(self, request: Request, future: Future[Any] | None) -> None:
        with self.lock:
            if self.dead:
                if future is not None:
                    future.set_exception(WorkerCrashed(self.name))
                return
            if future is not None:
                self.pending[request.id] = future
        self.outbox.put(request)

    def forget(self, request_id: int) -> None:
        with self.lock:
            self.pending.pop(request_id, None)

    @property
    def usable(self) -> bool:
        return not self.dead and self.proc.is_alive()

    @property
    def busy(self) -> bool:
        with self.lock:
            return bool(self.pending)

    def kill(self, *, graceful: bool) -> None:
        """End this generation; every unanswered request fails with WorkerCrashed."""
        with self.lock:
            self.dead = True
        if graceful:
            self.outbox.put(Request(0, SHUTDOWN, None))
            self.proc.join(5)
        if self.proc.is_alive():
            self.proc.terminate()
            self.proc.join(5)
        self.outbox.put(_STOP_SENDER)
        with contextlib.suppress(OSError):
            self.conn.close()  # unblocks a sender stuck writing to a hung child
        self._fail_all()

    def _send(self) -> None:
        while (item := self.outbox.get()) is not _STOP_SENDER:
            assert isinstance(item, Request)
            try:
                self.conn.send(item)
            except (OSError, EOFError, ValueError):
                break
        self._mark_dead()

    def _read(self) -> None:
        while True:
            try:
                response = self.conn.recv()
            except (EOFError, OSError, ValueError):
                break
            with self.lock:
                future = self.pending.pop(response.id, None)
            if future is None or future.done():
                continue
            if response.ok:
                future.set_result(response.payload)
            else:
                future.set_exception(WorkerError(response.error))
        self._mark_dead()

    def _mark_dead(self) -> None:
        with self.lock:
            self.dead = True
        self._fail_all()

    def _fail_all(self) -> None:
        with self.lock:
            pending, self.pending = self.pending, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(WorkerCrashed(self.name))


class Worker:
    def __init__(
        self,
        name: str,
        factory: str,
        config: Mapping[str, Any] | None = None,
        *,
        idle_timeout_s: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self._factory = factory
        self._config = dict(config or {})
        self._idle_timeout = idle_timeout_s
        self._clock = clock
        self._lock = threading.Lock()  # guards _gen and _last_used only; never held while sending
        self._ids = itertools.count(1)
        self._gen: _Generation | None = None
        self._last_used = clock()

    @property
    def alive(self) -> bool:
        gen = self._gen
        return gen is not None and gen.usable

    def submit(self, op: str, payload: Any) -> Future[Any]:
        return self._submit(op, payload)[1]

    def call(self, op: str, payload: Any, timeout: float | None = None) -> Any:
        """Send a request and wait. A missed deadline kills and replaces the worker."""
        gen, future, request_id = self._submit(op, payload)
        try:
            return future.result(timeout)
        except FutureTimeout:
            gen.forget(request_id)
            self._retire(gen)
            raise TimeoutError(f"{self.name} worker did not answer within {timeout} s") from None

    def stop_if_idle(self) -> bool:
        with self._lock:
            gen = self._gen
            idle = gen is not None and not gen.busy
            if not idle or self._clock() - self._last_used < self._idle_timeout:
                return False
            self._gen = None  # detach under the lock: no new request can reach it
        assert gen is not None
        gen.kill(graceful=True)
        return True

    def stop(self) -> None:
        with self._lock:
            gen, self._gen = self._gen, None
        if gen is not None:
            gen.kill(graceful=True)

    def _submit(self, op: str, payload: Any) -> tuple[_Generation, Future[Any], int]:
        future: Future[Any] = Future()
        with self._lock:
            if self._gen is None or not self._gen.usable:
                old, self._gen = self._gen, _Generation(self.name, self._factory, self._config)
                if old is not None:  # crashed or hung: make sure it is really gone
                    threading.Thread(
                        target=old.kill, kwargs={"graceful": False}, daemon=True
                    ).start()
            gen = self._gen
            request_id = next(self._ids)
            self._last_used = self._clock()
        gen.enqueue(Request(request_id, op, payload), future)
        return gen, future, request_id

    def _retire(self, gen: _Generation) -> None:
        with self._lock:
            if self._gen is gen:
                self._gen = None
        gen.kill(graceful=False)
