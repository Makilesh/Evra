"""A model worker process: started on first use, stopped when idle, restarted after a crash."""

from __future__ import annotations

import contextlib
import itertools
import multiprocessing
import sys
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any

if sys.platform == "win32":  # Pipe() gives a PipeConnection on Windows
    from multiprocessing.connection import PipeConnection as _Pipe
else:
    from multiprocessing.connection import Connection as _Pipe

from evra.workers.protocol import SHUTDOWN, Request, WorkerCrashed, WorkerError, worker_main


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
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._pending: dict[int, Future[Any]] = {}
        self._proc: BaseProcess | None = None
        self._conn: Connection | _Pipe | None = None
        self._reader: threading.Thread | None = None
        self._broken = False  # set by the reader when the pipe closes (the child is gone)
        self._last_used = clock()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    def submit(self, op: str, payload: Any) -> Future[Any]:
        future: Future[Any] = Future()
        with self._lock:
            self._ensure_started()
            assert self._conn is not None
            request_id = next(self._ids)
            self._pending[request_id] = future
            self._last_used = self._clock()
            try:
                self._conn.send(Request(request_id, op, payload))
            except (OSError, EOFError):
                self._pending.pop(request_id, None)
                future.set_exception(WorkerCrashed(self.name))
        return future

    def call(self, op: str, payload: Any, timeout: float | None = None) -> Any:
        return self.submit(op, payload).result(timeout)

    def stop_if_idle(self) -> bool:
        with self._lock:
            idle = not self._pending and self._clock() - self._last_used >= self._idle_timeout
        if idle and self.alive:
            self.stop()
            return True
        return False

    def stop(self) -> None:
        with self._lock:
            proc, conn, reader = self._proc, self._conn, self._reader
            self._proc = self._conn = self._reader = None
        if conn is not None:
            with contextlib.suppress(OSError, EOFError):
                conn.send(Request(0, SHUTDOWN, None))
        if proc is not None:
            proc.join(5)
            if proc.is_alive():
                proc.terminate()
                proc.join(5)
        if conn is not None:
            conn.close()
        if reader is not None:
            reader.join(5)

    def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.is_alive() and not self._broken:
            return
        if self._proc is not None:  # a crashed child: its pipe closed before is_alive() noticed
            self._proc.join(5)
            if self._proc.is_alive():
                self._proc.terminate()
        self._broken = False
        ctx = multiprocessing.get_context("spawn")
        parent, child = ctx.Pipe()
        proc = ctx.Process(
            target=worker_main,
            args=(child, self._factory, self._config),
            name=f"evra-{self.name}",
            daemon=True,
        )
        proc.start()
        child.close()
        self._proc, self._conn = proc, parent
        self._reader = threading.Thread(
            target=self._read, args=(parent,), name=f"{self.name}-reader", daemon=True
        )
        self._reader.start()

    def _read(self, conn: Connection | _Pipe) -> None:
        while True:
            try:
                response = conn.recv()
            except (EOFError, OSError):
                break
            with self._lock:
                future = self._pending.pop(response.id, None)
            if future is None:
                continue
            if response.ok:
                future.set_result(response.payload)
            else:
                future.set_exception(WorkerError(response.error))
        with self._lock:  # the process died or was stopped: nobody will answer these
            if self._conn is conn:
                self._broken = True
            pending, self._pending = self._pending, {}
        for future in pending.values():
            future.set_exception(WorkerCrashed(self.name))
