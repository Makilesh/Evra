"""Keep Windows awake while Evra records (BACKLOG, competitor review 2026-11-10).

A call app such as Teams usually keeps the PC awake, but an in-person 1:1 has nothing doing
that, so Windows could sleep mid-recording and cut the recording off. Evra asks for the system
only: the screen may still turn off. Windows ties the request to the thread that made it and
drops it when that thread ends, so a thread of its own holds it from the moment capture starts
until capture stops; the request also ends if the process exits.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import cast

import structlog

log = structlog.get_logger(__name__)

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
# SetThreadExecutionState: the new flags in, the previous state out (0 when it failed).
SetState = Callable[[int], int]


def windows_set_state() -> SetState | None:
    if sys.platform != "win32":
        return None
    import ctypes

    set_state = ctypes.windll.kernel32.SetThreadExecutionState
    set_state.argtypes = [ctypes.c_uint32]
    set_state.restype = ctypes.c_uint32
    return cast(SetState, set_state)


class KeepAwake:
    def __init__(self, set_state: SetState | None) -> None:
        """`set_state` is None where the OS has no such request: then nothing is held."""
        self._set_state = set_state
        self._release = threading.Event()
        self._thread: threading.Thread | None = None

    @classmethod
    def for_this_os(cls) -> KeepAwake:
        return cls(windows_set_state())

    def start(self) -> None:
        """Hold the PC awake; returns once the request is in place."""
        if self._set_state is None or self._thread is not None:
            return
        self._release.clear()
        held = threading.Event()
        self._thread = threading.Thread(
            target=self._hold, args=(self._set_state, held), name="keep-awake", daemon=True
        )
        self._thread.start()
        held.wait(timeout=1.0)

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is None:
            return
        self._release.set()
        thread.join(timeout=2.0)

    def _hold(self, set_state: SetState, held: threading.Event) -> None:
        if not set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
            log.warning("keep_awake_refused")
        held.set()
        self._release.wait()
        set_state(ES_CONTINUOUS)
