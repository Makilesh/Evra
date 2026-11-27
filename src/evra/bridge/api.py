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
from dataclasses import asdict
from pathlib import Path
from typing import Any, Protocol, TypedDict

import structlog

from evra.bridge.events import EventBus
from evra.capture.devices import MicList, list_mics
from evra.config import LlmSettings, Settings, Theme
from evra.llm.ollama import is_cloud_model_name
from evra.services.people import people_list
from evra.services.views import clean_title, meeting_detail, meeting_list
from evra.store.db import connect, writing
from evra.store.items import ItemStore
from evra.store.meetings import MeetingStore
from evra.store.notepad import LineIn, NotepadStore
from evra.store.people import NameRefused, Person, PersonStore
from evra.store.speakers import SpeakerStore

log = structlog.get_logger(__name__)

# An Ollama model name ("gemma4:12b", "hf.co/user/model:Q4_K_M"): no spaces, no control characters.
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}")
THEMES: dict[str, Theme] = {"light": "light", "dark": "dark", "system": "system"}


def open_folder(path: Path) -> None:
    """Show a folder in Explorer: a local program, nothing is served or sent."""
    if sys.platform != "win32":
        raise OSError("folders open only on Windows")
    os.startfile(path)


def _person(person: Person) -> dict[str, str]:
    return {"id": person.id, "name": person.name}


def _typed_lines(raw: object) -> list[LineIn] | None:
    """The window's notepad lines, or None when anything has the wrong shape or type."""
    if not isinstance(raw, list):
        return None
    lines: list[LineIn] = []
    for entry in raw:
        if not isinstance(entry, dict) or "captured_at" not in entry:
            return None
        line_id, text, at, pasted = (entry.get(k) for k in ("id", "text", "captured_at", "pasted"))
        if not (isinstance(line_id, str) and isinstance(text, str) and isinstance(pasted, bool)):
            return None
        if at is not None and (not isinstance(at, int) or isinstance(at, bool)):
            return None
        lines.append(LineIn(line_id, text, at, pasted))
    return lines


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


class Asker(Protocol):
    def ask(self, meeting_id: object, question: object) -> dict[str, Any]: ...

    def prepare(self, meeting_id: object) -> dict[str, Any]: ...


class Briefer(Protocol):
    def person_page(self, person_id: object) -> dict[str, Any] | None: ...

    def write_brief(self, person_id: object) -> dict[str, Any]: ...


class BridgeApi:
    def __init__(
        self,
        *,
        app_name: str,
        version: str,
        bus: EventBus,
        control: Control,
        db_path: Path,
        asker: Asker | None = None,
        people: Briefer | None = None,
        mic_lister: Callable[[], MicList] = list_mics,
        folder_opener: Callable[[Path], None] = open_folder,
    ) -> None:
        self._app_name = app_name
        self._version = version
        self._bus = bus
        self._control = control
        self._asker = asker
        self._people = people
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
            return meeting_list(conn)

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

    def ask_meeting(self, meeting_id: str, question: str) -> dict[str, Any]:
        if self._asker is None or not isinstance(meeting_id, str) or not isinstance(question, str):
            return {"ok": False, "reason": "invalid"}
        return self._asker.ask(meeting_id, question)

    def prepare_ask(self, meeting_id: str) -> dict[str, Any]:
        if self._asker is None or not isinstance(meeting_id, str):
            return {"ok": False}
        return self._asker.prepare(meeting_id)

    def save_notes(self, meeting_id: str, lines: list[Any]) -> dict[str, Any]:
        """The meeting's notepad as it is now (BUILD.md §7.1), saved whole. Every entry must be
        {"id": str, "text": str, "captured_at": epoch ms or null, "pasted": bool}, or nothing
        is saved. The lines are content: logs get the meeting and a count."""
        typed = _typed_lines(lines) if isinstance(meeting_id, str) else None
        if typed is None:
            return {"ok": False}
        try:
            with self._db() as conn:
                NotepadStore(conn).replace(meeting_id, typed)
        except (KeyError, ValueError) as exc:  # no such meeting, or past the pad's limits
            reason = type(exc).__name__
            log.info("notes_refused", meeting_id=meeting_id, lines=len(typed), reason=reason)
            return {"ok": False}
        except sqlite3.Error as exc:  # e.g. busy: the window saves again on the next change
            log.warning("notes_not_saved", meeting_id=meeting_id, error=type(exc).__name__)
            return {"ok": False}
        return {"ok": True}

    def set_item_status(self, item_id: str, status: str) -> dict[str, Any]:
        """Tick an action item done (or open it again, or dismiss it). A saved change changes
        the open promises, so the window is told to read them again."""
        if not isinstance(item_id, str) or not isinstance(status, str):
            return {"ok": False}
        with self._db() as conn:
            saved = ItemStore(conn).set_status(item_id, status)
        if saved:
            self._bus.emit("promises.changed", {})
        return {"ok": saved}

    def list_promises(self) -> dict[str, list[dict[str, Any]]]:
        """Every open promise across the 1:1s, newest meeting first: what the owner promised
        ("you") and what the other person did ("them"). Each names who the 1:1 was with
        ({"id", "name"}, or null) and the first transcript line it cites."""
        with self._db() as conn:
            promises = ItemStore(conn).open_promises()
        return {
            "you": [asdict(p) for p in promises if p.owner == "You"],
            "them": [asdict(p) for p in promises if p.owner == "Them"],
        }

    def rename_meeting(self, meeting_id: str, title: str) -> dict[str, Any]:
        cleaned = clean_title(title) if isinstance(title, str) else None
        if not isinstance(meeting_id, str) or cleaned is None:
            return {"ok": False}
        with self._db() as conn:
            return {"ok": MeetingStore(conn).rename_meeting(meeting_id, cleaned)}

    # --- people: who each 1:1 was with (BUILD.md §6.5, D14). Names are content: logs get ids.

    def set_meeting_person(self, meeting_id: str, name: str | None) -> dict[str, Any]:
        """Say who a 1:1 was with, by name: the person with that name, whatever its case or
        spacing, else a new one; None or "" says no one. "You" is the owner's ("reserved"); an
        empty or too long name is "invalid". The person is made and linked in one transaction,
        so a refused link leaves no one behind."""
        if not isinstance(meeting_id, str):
            return {"ok": False}
        if name is not None and not isinstance(name, str):
            return {"ok": False, "reason": "invalid"}
        try:
            with self._db() as conn, writing(conn):
                person = PersonStore(conn).find_or_create(name) if name else None
                SpeakerStore(conn).set_person(meeting_id, None if person is None else person.id)
        except NameRefused as exc:
            return {"ok": False, "reason": exc.reason}
        except KeyError:  # no such meeting
            return {"ok": False}
        log.info("meeting_person_set", meeting_id=meeting_id, named=person is not None)
        self._bus.emit("promises.changed", {})  # each promise names who its 1:1 was with
        return {"ok": True, "with": None if person is None else _person(person)}

    def list_people(self) -> list[dict[str, Any]]:
        """Everyone the owner has named, by name, each with when their last 1:1 started
        (`last_met`, epoch ms, or null)."""
        with self._db() as conn:
            return people_list(conn)

    def person_page(self, person_id: str) -> dict[str, Any] | None:
        """A person's page: their last 1:1's points for next time and open questions, their
        brief and their 1:1s. Their open promises are the Promises page's (`list_promises`)."""
        if self._people is None or not isinstance(person_id, str):
            return None
        return self._people.person_page(person_id)

    def write_brief(self, person_id: str) -> dict[str, Any]:
        """Start a person's prep brief; it arrives as `brief.updated`."""
        if self._people is None or not isinstance(person_id, str):
            return {"ok": False, "reason": "invalid"}
        return self._people.write_brief(person_id)

    def rename_person(self, person_id: str, name: str) -> dict[str, Any]:
        """A person's new name, everywhere they show; "taken" when someone else has it."""
        if not isinstance(person_id, str):
            return {"ok": False, "reason": "unknown"}
        if not isinstance(name, str):
            return {"ok": False, "reason": "invalid"}
        with self._db() as conn:
            result = PersonStore(conn).rename(person_id, name)
        return {"ok": True} if result == "ok" else {"ok": False, "reason": result}

    def remove_person(self, person_id: str) -> dict[str, Any]:
        """Forget a person: their meetings say "Them" again."""
        if not isinstance(person_id, str):
            return {"ok": False}
        with self._db() as conn:
            return {"ok": PersonStore(conn).remove(person_id)}

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
        chosen = THEMES.get(theme) if isinstance(theme, str) else None
        if chosen is None:
            return {"ok": False}
        return {"ok": self._control.set_theme(chosen)}

    def set_note_model(self, model: str) -> dict[str, Any]:
        if not isinstance(model, str) or not MODEL_NAME.fullmatch(model):
            return {"ok": False}
        if is_cloud_model_name(model):
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
