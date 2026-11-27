"""A person's page and their prep brief (Plan C Task 3): the page's payload, the brief written on
a daemon thread and announced with `brief.updated`, one job at a time with asking."""

import json
import sqlite3
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from evra.config import LlmSettings
from evra.llm.provider import ChatMessage, ChatResult, LlmProvider, LlmUnavailable
from evra.notes.extract import CheckedItem, ItemKind
from evra.notes.validate import CheckedBullet, CheckedNote, CheckedSection
from evra.paths import AppPaths
from evra.services.ask import AskService, JobSlot
from evra.services.people import PeopleService, open_items
from evra.store.db import connect
from evra.store.items import Promise
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
        next_time: Sequence[str] = (),
        items: Sequence[Item] = (),
    ) -> None:
        """The meeting's note: its summary cites the first line, "for next time" the last."""
        lines = self.lines[mid]
        sections = (
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


def _wait_for(heard: list[object]) -> None:
    deadline = time.monotonic() + 10
    while not heard:
        assert time.monotonic() < deadline
        time.sleep(0.01)


def test_person_page_shows_their_meetings_last_time_and_brief(tmp_path: Path) -> None:
    f = Folder(tmp_path)
    page = f.service().person_page(f.priya.id)
    assert page is not None
    assert set(page) == {"person", "last", "brief", "meetings"}  # promises: the window's (RC7)
    assert page["person"] == {"id": f.priya.id, "name": "Priya"}
    assert [(m["id"], m["has_note"], m["with_name"]) for m in page["meetings"]] == [
        (f.unnoted, False, "Priya"),
        (f.latest, True, "Priya"),
        (f.older, True, "Priya"),
    ]
    # the newest 1:1 that has a note: what was left for next time, and what is still open
    last = page["last"]
    assert (last["meeting_id"], last["title"], last["started_at"]) == (
        f.latest,
        "Weekly 1:1",
        LATEST,
    )
    line = {"utterance_id": f.lines[f.latest][3], "start_ms": 30_000}
    assert last["next_time"] == [{"text": "Mentoring a new hire.", "citations": [line]}]
    [question] = last["open_questions"]
    assert question["text"] == "Can the limit go to 500 requests?"
    assert question["item"]["kind"] == "open_question"
    assert page["brief"] is None
    json.dumps(page)
    assert f.service().person_page("nobody") is None
    assert f.service().person_page(5) is None


def test_brief_needs_notes(tmp_path: Path) -> None:
    """Review focus 4: someone with no note from a 1:1 yet is told so, without a call."""
    f = Folder(tmp_path)
    conn = connect(f.paths.db_path)
    dana = PersonStore(conn).find_or_create("Dana")  # no 1:1 at all
    lee = PersonStore(conn).find_or_create("Lee")
    f.meeting(conn, lee, "Recording 2026-11-27 09:00", UNNOTED)  # a 1:1, but no note yet
    conn.close()
    provider = FakeProvider([])
    service = f.service(provider)
    for person in (dana, lee, dana):  # a refusal frees the slot: never "busy" after one
        assert service.write_brief(person.id) == {"ok": False, "reason": "no_notes"}
    assert service.write_brief("nobody") == {"ok": False, "reason": "unknown"}
    assert service.write_brief(5) == {"ok": False, "reason": "invalid"}
    assert provider.calls == [] and f.events == []


def test_a_written_brief_is_saved_and_announced(tmp_path: Path) -> None:
    f = Folder(tmp_path)
    provider = FakeProvider([GOOD])
    service = f.service(provider)
    assert service.write_brief(f.priya.id) == {"ok": True}
    payload = f.wait_event()
    assert (payload["person_id"], payload["state"]) == (f.priya.id, "written")
    brief = payload["brief"]
    assert brief["points"] == [
        {
            "text": "You will send the vendor quote by Friday.",
            "meetings": [{"id": f.latest, "title": "Weekly 1:1", "started_at": LATEST}],
        },
        {
            "text": "Twelve thousand dollars are left for contractors.",
            "meetings": [{"id": f.older, "title": "Budget check", "started_at": OLDER}],
        },
    ]
    page = service.person_page(f.priya.id)
    assert page is not None and page["brief"] == brief
    # m:1 is their latest note, m:2 the one before; a 1:1 with no note and Sam's are not read
    system, user = (m.content for m in provider.calls[0])
    assert (
        "<notes>\n[m:1] Weekly 1:1 · 2026-11-24\n"
        "- You will send the vendor quote by Friday.\n- Mentoring a new hire.\n</notes>"
    ) in system
    assert "[m:2] Budget check · 2026-11-17" in system and "[m:3]" not in system
    assert "hiring" not in system.lower()
    assert "1:1 with Priya," in user
    assert (
        "4. Open promises still on the owner's list: "
        "You: Send the vendor quote (due by Friday); Priya: Tell marketing\n"
    ) in user
    # a meeting renamed later shows its new name
    conn = connect(f.paths.db_path)
    MeetingStore(conn).rename_meeting(f.older, "Contractor budget")
    conn.close()
    page = service.person_page(f.priya.id)
    assert page is not None
    assert page["brief"]["points"][1]["meetings"][0]["title"] == "Contractor budget"


def test_unchecked_brief_is_not_shown(tmp_path: Path) -> None:
    """Review focus 4: a brief whose every point fails the check is not shown, and does not
    replace the one before."""
    f = Folder(tmp_path)
    service = f.service(FakeProvider([GOOD, reply(("Marcus approved 9,000 dollars.", ["m:1"]))]))
    service.write_brief(f.priya.id)
    written = f.wait_event()["brief"]
    assert service.write_brief(f.priya.id) == {"ok": True}
    assert f.wait_event() == {"person_id": f.priya.id, "state": "unchecked"}
    page = service.person_page(f.priya.id)
    assert page is not None and page["brief"] == written


def test_the_brief_reads_the_three_newest_notes(tmp_path: Path) -> None:
    f = Folder(tmp_path)
    conn = connect(f.paths.db_path)
    for n in range(2):  # two more noted 1:1s, older than the rest
        mid = f.meeting(conn, f.priya, f"Kick-off {n}", OLDER - (n + 1) * 86_400_000)
        f.note(conn, mid, [f"Kick-off point {n}."])
    conn.close()
    provider = FakeProvider([GOOD])
    f.service(provider).write_brief(f.priya.id)
    f.wait_event()
    system = provider.calls[0][0].content
    assert [line.split(" · ")[0] for line in system.splitlines() if line.startswith("[m:")] == [
        "[m:1] Weekly 1:1",
        "[m:2] Budget check",
        "[m:3] Kick-off 0",
    ]


def test_open_items_name_who_owes_them() -> None:
    priya, sam = Person("p1", "Priya Shah"), Person("p2", "Sam")

    def promise(
        text: str, them: bool, due: str | None = None, to: Person | None = priya
    ) -> Promise:
        owner = "Them" if them else "You"
        return Promise("i", text, due, owner, "m", "t", 1, to, None, None)

    promises = [
        promise("Send the quote", False, "by Friday"),
        promise("Them: tell marketing", True),  # led by its owner already: said once
        promise("Priya Shah: book the room", True),
        promise("Book the offsite by Monday", False, "by Monday"),  # its due date said once
        promise("Review the loop", True, to=sam),
        promise("Share the deck", False, to=None),
    ]
    assert open_items(promises, priya) == [
        "You: Send the quote (due by Friday)",
        "Priya Shah: tell marketing",
        "Priya Shah: book the room",
        "You: Book the offsite by Monday",
    ]


def test_a_brief_shares_the_busy_rule_with_asking(tmp_path: Path) -> None:
    f = Folder(tmp_path)
    slot = JobSlot()
    heard: list[object] = []
    brief = Blocking([GOOD])
    people = f.service(brief, slot=slot)
    asker = f.asker(FakeProvider([NOT_FOUND]), slot, heard)
    assert people.write_brief(f.priya.id) == {"ok": True}
    assert asker.ask(f.latest, "What did I promise?") == {"ok": False, "reason": "busy"}
    assert asker.prepare(f.latest) == {"ok": False}
    assert people.write_brief(f.sam.id) == {"ok": False, "reason": "busy"}
    brief.release.set()
    assert f.wait_event()["state"] == "written"
    # and a question being answered holds a brief back the same way
    question = Blocking([NOT_FOUND])
    asker = f.asker(question, slot, heard)
    assert asker.ask(f.latest, "What did I promise?")["ok"] is True
    assert people.write_brief(f.priya.id) == {"ok": False, "reason": "busy"}
    question.release.set()
    _wait_for(heard)
    # the app closing refuses both (AskService.shutdown closes the shared slot)
    asker.shutdown()
    assert people.write_brief(f.priya.id) == {"ok": False, "reason": "busy"}


def test_a_failed_brief_says_why_and_frees_the_slot(tmp_path: Path) -> None:
    class Down(FakeProvider):
        def chat_json(self, *args: Any, **kwargs: Any) -> ChatResult:
            raise LlmUnavailable("down")

    f = Folder(tmp_path)
    service = f.service(Down([]))
    for _ in range(2):  # the slot is free again after a failure
        assert service.write_brief(f.priya.id) == {"ok": True}
        assert f.wait_event() == {
            "person_id": f.priya.id,
            "state": "failed",
            "reason": "ollama_down",
        }

    def broken(_s: LlmSettings) -> LlmProvider:
        raise RuntimeError("x")

    service = f.service(provider_factory=broken)
    assert service.write_brief(f.priya.id) == {"ok": True}
    assert f.wait_event() == {"person_id": f.priya.id, "state": "failed", "reason": "llm_error"}
    page = service.person_page(f.priya.id)
    assert page is not None and page["brief"] is None


def test_a_brief_for_someone_forgotten_meanwhile_is_not_kept(tmp_path: Path) -> None:
    f = Folder(tmp_path)
    blocking = Blocking([GOOD])
    f.service(blocking).write_brief(f.priya.id)
    conn = connect(f.paths.db_path)
    try:
        assert PersonStore(conn).remove(f.priya.id) is True
        blocking.release.set()
        assert f.wait_event() == {"person_id": f.priya.id, "state": "failed", "reason": "unknown"}
        assert conn.execute("SELECT count(*) FROM brief").fetchone()[0] == 0
    finally:
        conn.close()


def test_names_and_brief_text_never_reach_the_log(tmp_path: Path) -> None:
    f = Folder(tmp_path)
    service = f.service(FakeProvider([GOOD]))
    with structlog.testing.capture_logs() as logs:
        service.person_page(f.priya.id)
        service.write_brief(f.priya.id)
        f.wait_event()
        service.write_brief("nobody")
    assert {e["event"] for e in logs} <= {"brief_started", "brief_written"}
    dumped = json.dumps(logs).lower()
    for content in ("priya", "quote", "marketing", "contractors", "weekly"):
        assert content not in dumped
