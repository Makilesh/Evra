"""Methods React can call as window.pywebview.api.<name>(...) (M0, M3c spec §3.3).

pywebview exposes every public attribute, so keep state in underscore attributes. Each call
runs on its own thread, so each opens its own database connection. Arguments come from
JavaScript: anything of the wrong type is refused, never trusted.
"""

from __future__ import annotations

import contextlib
import os
import re
import sqlite3
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Protocol, TypedDict

import structlog

from evra.bridge.events import EventBus
from evra.capture.devices import MicList, list_mics
from evra.config import LlmSettings, Settings, Theme
from evra.services.views import clean_title, meeting_detail, meeting_summary
from evra.store.db import connect
from evra.store.meetings import MeetingStore

log = structlog.get_logger(__name__)

# An Ollama model name ("gemma4:12b", "hf.co/user/model:Q4_K_M"): no spaces, no control characters.
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}")
THEMES: tuple[Theme, ...] = ("light", "dark")


def open_folder(path: Path) -> None:
    """Show a folder in Explorer: a local program, nothing is served or sent."""
    if sys.platform != "win32":
        raise OSError("folders open only on Windows")
    os.startfile(path)


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

    @property
    def settings(self) -> Settings: ...

    def set_theme(self, theme: Theme) -> bool: ...

    def set_note_model(self, model: str) -> bool: ...

    def note_models(self) -> dict[str, Any]: ...


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
        folder_opener: Callable[[Path], None] = open_folder,
    ) -> None:
        self._app_name = app_name
        self._version = version
        self._bus = bus
        self._control = control
        self._db_path = db_path
        self._mic_lister = mic_lister
        self._open_folder = folder_opener

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

    # --- settings --------------------------------------------------------------------------

    def get_settings(self) -> dict[str, Any]:
        settings = self._control.settings
        return {
            "theme": settings.theme,
            "note_model": settings.llm.model,
            "default_note_model": LlmSettings().model,
            "data_dir": str(self._db_path.parent),
            "version": self._version,
        }

    def set_theme(self, theme: str) -> dict[str, Any]:
        if theme not in THEMES:
            return {"ok": False}
        return {"ok": self._control.set_theme("dark" if theme == "dark" else "light")}

    def set_note_model(self, model: str) -> dict[str, Any]:
        if not isinstance(model, str) or not MODEL_NAME.fullmatch(model):
            return {"ok": False}
        return {"ok": self._control.set_note_model(model)}

    def list_note_models(self) -> dict[str, Any]:
        return self._control.note_models()

    def open_data_folder(self) -> dict[str, Any]:
        try:
            self._open_folder(self._db_path.parent)
        except OSError as exc:
            log.warning("data_folder_not_opened", error=type(exc).__name__)
            return {"ok": False}
        return {"ok": True}

    @contextlib.contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = connect(self._db_path)
        try:
            yield conn
        finally:
            conn.close()
