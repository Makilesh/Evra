"""The people service under test (Plan C Task 3): a data folder with Priya's three 1:1s (the
newest without a note) and Sam's one, the events the service sends, and a provider that answers
only when told. Shared by test_people_service.py."""

import json
import sqlite3
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from evra.config import LlmSettings
from evra.llm.provider import ChatMessage, ChatResult, LlmProvider
from evra.notes.extract import CheckedItem, ItemKind
from evra.notes.validate import CheckedBullet, CheckedNote, CheckedSection
from evra.paths import AppPaths
from evra.services.ask import AskService, JobSlot
from evra.services.people import PeopleService
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore
from evra.store.people import Person, PersonStore
from evra.store.speakers import SpeakerStore
from tests.unit.notes.fakes import FakeProvider

OLDER = int(datetime(2026, 11, 17, 10, 0).timestamp() * 1000)
LATEST = int(datetime(2026, 11, 24, 10, 0).timestamp() * 1000)
UNNOTED = int(datetime(2026, 11, 26, 10, 0).timestamp() * 1000)
SPOKEN = [
    (1, 1_000, "Can you send me the vendor quote by Friday?"),
    (0, 5_000, "Yes, I will."),
    (1, 9_000, "Can we raise the limit to 500 requests?"),
    (1, 30_000, "Let's pick up mentoring next time."),
]
NOT_FOUND = json.dumps({"found": False, "points": []})
# A record of a note: its kind, text, the lines it cites (by their place), owner and due date.
Item = tuple[ItemKind, str, tuple[int, ...], str | None, str | None]


def reply(*points: tuple[str, list[str]]) -> str:
    return json.dumps({"points": [{"text": t, "citations": c} for t, c in points]})


GOOD = reply(
    ("You will send the vendor quote by Friday.", ["m:1"]),
    ("Twelve thousand dollars are left for contractors.", ["m:2"]),
)


class Folder:
    """A data folder: Priya's three 1:1s (the newest has no note yet) and Sam's one."""

    def __init__(self, tmp_path: Path) -> None:
        self.paths = AppPaths.under(tmp_path)
        self.paths.ensure()
        self.lines: dict[str, list[str]] = {}  # each meeting's transcript line ids
        conn = connect(self.paths.db_path)
        migrate(conn)
        people = PersonStore(conn)
        self.priya, self.sam = people.find_or_create("Priya"), people.find_or_create("Sam")
        self.older = self.meeting(conn, self.priya, "Budget check", OLDER)
        self.note(conn, self.older, ["Twelve thousand dollars are left for contractors."])
        self.latest = self.meeting(conn, self.priya, "Weekly 1:1", LATEST)
        self.note(
            conn,
            self.latest,
            ["You will send the vendor quote by Friday."],
            next_time=["Mentoring a new hire."],
            items=[
                ("action_item", "Send the vendor quote", (0, 1), "You", "by Friday"),
                ("action_item", "Tell marketing", (0,), "Them", None),
                ("open_question", "Can the limit go to 500 requests?", (2,), None, None),
            ],
        )
        self.unnoted = self.meeting(conn, self.priya, "Recording 2026-11-26 10:00", UNNOTED)
        self.hiring = self.meeting(conn, self.sam, "Hiring sync", LATEST + 3_600_000)
        self.note(
            conn,
            self.hiring,
            ["Sam reviews the hiring loop."],
            items=[("action_item", "Review the hiring loop", (0,), "Them", None)],
        )
        conn.close()
        self.events: list[tuple[str, Mapping[str, Any]]] = []
        self.got = threading.Event()

    def meeting(self, conn: sqlite3.Connection, person: Person, title: str, started: int) -> str:
        """A finished 1:1 with the person, four lines long."""
        store = MeetingStore(conn)
        mid = store.create_meeting(
            title=title,
            mode="one_on_one",
            situation="call_headphones",
            template="one_on_one",
            started_at_ms=started,
        )
        vid = store.create_transcript_version(mid, kind="live", model="fake")
        self.lines[mid] = [
            store.add_utterance(
                version_id=vid, meeting_id=mid, channel=ch, start_ms=s, end_ms=s + 2_000, text=t
            ).id
            for ch, s, t in SPOKEN
        ]
        SpeakerStore(conn).set_person(mid, person.id)
        return mid

    def note(
        self,
        conn: sqlite3.Connection,
        mid: str,
        summary: Sequence[str],
        *,
        discussion: Sequence[str] = (),
        next_time: Sequence[str] = (),
        items: Sequence[Item] = (),
    ) -> None:
        """The meeting's note: its summary and discussion cite the first line, "for next time"
        the last."""
        lines = self.lines[mid]
        sections = (
            CheckedSection(
                "discussion", "Discussion", tuple(CheckedBullet(t, (lines[0],)) for t in discussion)
            ),
            CheckedSection(
                "next_time",
                "For next time",
                tuple(CheckedBullet(t, (lines[3],)) for t in next_time),
            ),
        )
        NoteStore(conn).save_generation(
            meeting_id=mid,
            transcript_version_id=MeetingStore(conn).current_transcript_version(mid) or "",
            note=CheckedNote(
                tuple(CheckedBullet(t, (lines[0],)) for t in summary), sections, 1, 0, {}
            ),
            provider="fake",
            model="fake:1b",
            prompt_version="a0-v1+a1-v4+a4-v2",
            template="one_on_one",
            tokens_in=1,
            tokens_out=1,
            items=[
                CheckedItem(kind, text, tuple(lines[n] for n in cites), owner, due, 0.9)
                for kind, text, cites, owner, due in items
            ],
        )

    def emit(self, name: str, payload: Mapping[str, Any]) -> bool:
        self.events.append((name, payload))
        self.got.set()
        return True

    def service(self, provider: LlmProvider | None = None, **kw: Any) -> PeopleService:
        args: dict[str, Any] = {
            "paths": self.paths,
            "llm": lambda: LlmSettings(model="fake:1b"),
            "emit": self.emit,
            "slot": JobSlot(),
            "recording_busy": lambda: False,
            "note_busy": lambda: False,
            "provider_factory": lambda _s: provider or FakeProvider([]),
        }
        args.update(kw)
        return PeopleService(**args)

    def asker(self, provider: LlmProvider, slot: JobSlot, heard: list[object]) -> AskService:
        return AskService(
            paths=self.paths,
            llm=lambda: LlmSettings(model="fake:1b"),
            emit=lambda _name, payload: heard.append(payload),
            recording_busy=lambda: False,
            note_busy=lambda: False,
            provider_factory=lambda _s: provider,
            slot=slot,
        )

    def wait_event(self) -> Mapping[str, Any]:
        assert self.got.wait(10)
        self.got.clear()
        name, payload = self.events[-1]
        assert name == "brief.updated"
        return payload


class Blocking(FakeProvider):
    """Answers only once `release` is set."""

    def __init__(self, replies: list[str]) -> None:
        super().__init__(replies)
        self.release = threading.Event()

    def chat_json(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        schema: Mapping[str, Any],
        *,
        max_output_tokens: int | None = None,
    ) -> ChatResult:
        assert self.release.wait(10)
        return super().chat_json(model, messages, schema, max_output_tokens=max_output_tokens)


def wait_for(heard: list[object]) -> None:
    deadline = time.monotonic() + 10
    while not heard:
        assert time.monotonic() < deadline
        time.sleep(0.01)
