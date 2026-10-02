"""Methods React can call as window.pywebview.api.<name>(...) (M0, M3c spec §3.3).

pywebview exposes every public attribute, so keep state in underscore attributes. Each call
runs on its own thread, so each opens its own database connection. Arguments come from
JavaScript: anything of the wrong type is refused, never trusted.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Protocol, TypedDict

import structlog

from evra.bridge.events import EventBus
from evra.capture.devices import MicList, list_mics
from evra.services.views import clean_title, meeting_detail, meeting_summary
from evra.store.db import connect
from evra.store.meetings import MeetingStore

log = structlog.get_logger(__name__)


class PingReply(TypedDict):
    reply: str


class AppInfoDict(TypedDict):
    name: str
    version: str


class Control(Protocol):
    @property
    def mic_name(self) -> str: ...

    def start(self, mic_name: str) -> dict[str, Any]: ...

    def stop(self) -> dict[str, Any]: ...

    def write_note(self, meeting_id: str) -> dict[str, Any]: ...

    def state(self) -> dict[str, Any]: ...


class BridgeApi:
    def __init__(
        self,
        *,
        app_name: str,
        version: str,
        bus: EventBus,
        control: Control,
        db_path: Path,
        mic_lister: Callable[[], MicList] = list_mics,
    ) -> None:
        self._app_name = app_name
        self._version = version
        self._bus = bus
        self._control = control
        self._db_path = db_path
        self._mic_lister = mic_lister

    def ping(self, message: str) -> PingReply:
        return {"reply": f"pong: {message}"}

    def app_info(self) -> AppInfoDict:
        return {"name": self._app_name, "version": self._version}

    def request_hello(self) -> None:
        """Proves the Python -> React push path."""
        self._bus.emit("app.hello", {"message": "Python is connected"})

    def list_meetings(self) -> list[dict[str, Any]]:
        with self._db() as conn:
            return [meeting_summary(row) for row in MeetingStore(conn).list_meetings()]

    def get_meeting(self, meeting_id: str) -> dict[str, Any] | None:
        if not isinstance(meeting_id, str):
            return None
        with self._db() as conn:
            return meeting_detail(conn, meeting_id)

    def list_mics(self) -> dict[str, Any]:
        try:
            mics = self._mic_lister()
        except Exception as exc:  # no audio stack: the Windows default mic still works
            log.warning("mics_not_listed", error=type(exc).__name__)
            mics = MicList("", ())
        return {"default": mics.default, "mics": list(mics.mics), "chosen": self._control.mic_name}

    def start_recording(self, mic_name: str) -> dict[str, Any]:
        if not isinstance(mic_name, str):
            return {"ok": False, "reason": "invalid"}
        return self._control.start(mic_name)

    def stop_recording(self) -> dict[str, Any]:
        return self._control.stop()

    def write_note(self, meeting_id: str) -> dict[str, Any]:
        if not isinstance(meeting_id, str):
            return {"ok": False}
        return self._control.write_note(meeting_id)

    def rename_meeting(self, meeting_id: str, title: str) -> dict[str, Any]:
        cleaned = clean_title(title) if isinstance(title, str) else None
        if not isinstance(meeting_id, str) or cleaned is None:
            return {"ok": False}
        with self._db() as conn:
            return {"ok": MeetingStore(conn).rename_meeting(meeting_id, cleaned)}

    def recording_state(self) -> dict[str, Any]:
        return self._control.state()

    @contextlib.contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = connect(self._db_path)
        try:
            yield conn
        finally:
            conn.close()
