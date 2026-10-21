"""Messages between the app and a model worker process (BUILD.md §4.2).

Errors cross the pipe as the exception *type* only: messages can quote meeting content.
"""

from __future__ import annotations

import importlib
import signal
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Any

SHUTDOWN = "__shutdown__"
Handler = Callable[[str, Any], Any]


@dataclass(frozen=True)
class Request:
    id: int
    op: str
    payload: Any


@dataclass(frozen=True)
class Response:
    id: int
    ok: bool
    payload: Any = None
    error: str = ""


class WorkerCrashed(RuntimeError):
    """The worker process died before answering."""


class WorkerError(RuntimeError):
    def __init__(self, error_type: str) -> None:
        super().__init__(f"worker raised {error_type}")
        self.error_type = error_type


def serve(conn: Connection, handler: Handler) -> None:
    while True:
        try:
            request = conn.recv()
        except (EOFError, OSError):
            return
        if request.op == SHUTDOWN:
            return
        try:
            conn.send(Response(request.id, True, handler(request.op, request.payload)))
        except Exception as exc:  # report the type only
            conn.send(Response(request.id, False, error=type(exc).__name__))


def worker_main(conn: Connection, factory: str, config: dict[str, Any]) -> None:
    """Entry point of a spawned worker: build the handler named "module:function", then serve.

    Ctrl+C reaches every process on the console; the app owns the worker's lifetime, so the
    worker ignores it (otherwise it dies mid-request and prints a traceback).
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    module_name, _, attr = factory.partition(":")
    handler: Handler = getattr(importlib.import_module(module_name), attr)(**config)
    serve(conn, handler)
