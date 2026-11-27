"""A person's page and their prep brief (Plan C Task 3): the page's payload, the brief written on
a daemon thread and announced with `brief.updated`, one job at a time with asking."""

import json
from pathlib import Path
from typing import Any

import structlog

from evra.config import LlmSettings
from evra.llm.provider import ChatResult, LlmProvider, LlmUnavailable
from evra.services.ask import JobSlot
from evra.services.people import open_items
from evra.store.db import connect
from evra.store.items import ItemStore, Promise
from evra.store.meetings import MeetingStore
from evra.store.notes import NoteStore
from evra.store.people import Person, PersonStore
from tests.unit.notes.fakes import FakeProvider
from tests.unit.services.people_harness import (
    GOOD,
    LATEST,
    NOT_FOUND,
    OLDER,
    UNNOTED,
    Blocking,
    Folder,
    reply,
    wait_for,
)


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
        "- You will send the vendor quote by Friday.\n- Mentoring a new hire.\n"
        "- You: Send the vendor quote (due by Friday)\n- Them: Tell marketing\n"
        "- Open question: Can the limit go to 500 requests?\n</notes>"
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


def test_the_brief_reads_each_note_with_its_open_records(tmp_path: Path) -> None:
    """RC8: a source is the note's points, then its records still open (decisions, tasks led
    once by who owes them, open questions), so a promise kept only as a record can be cited."""
    f = Folder(tmp_path)
    conn = connect(f.paths.db_path)
    lee = PersonStore(conn).find_or_create("Lee")
    mid = f.meeting(conn, lee, "Planning", LATEST)
    f.note(
        conn,
        mid,
        [],
        discussion=["The hiring plan is on track."],
        next_time=["Mentoring a new hire."],
        items=[
            ("decision", "Hire two contractors.", (0,), None, None),
            ("action_item", "Send the vendor quote", (0, 1), "You", "Friday"),
            ("action_item", "Ask finance about the laptops", (0,), "Them", None),
            ("action_item", "Book the room", (0,), "You", None),  # done below
            ("action_item", "Order the badges", (0,), "Them", None),  # set aside below
            ("open_question", "Can the limit go to 500 requests?", (2,), None, None),
        ],
    )
    items, note = ItemStore(conn), NoteStore(conn).current_note(mid)
    assert note is not None
    ids = {item.text: item.id for item in items.for_generation(note.generation_id)}
    items.set_status(ids["Book the room"], "done")
    items.set_status(ids["Order the badges"], "dismissed")
    conn.close()
    provider = FakeProvider([reply(("Lee will ask finance about the laptops.", ["m:1"]))])
    f.service(provider).write_brief(lee.id)
    payload = f.wait_event()
    system = provider.calls[0][0].content
    assert (
        "<notes>\n[m:1] Planning · 2026-11-24\n"
        "- The hiring plan is on track.\n- Mentoring a new hire.\n"
        "- Decision: Hire two contractors.\n- You: Send the vendor quote (due Friday)\n"
        "- Them: Ask finance about the laptops\n"
        "- Open question: Can the limit go to 500 requests?\n</notes>"
    ) in system
    assert "Book the room" not in system and "Order the badges" not in system
    # a point stating the promise kept only as a record passes the check against it
    assert payload["state"] == "written"
    texts = [p["text"] for p in payload["brief"]["points"]]
    assert texts == ["Lee will ask finance about the laptops."]


def test_a_brief_waits_for_the_recording(tmp_path: Path) -> None:
    """RC9: while a recording loads, runs or stops, a brief is refused as a question is: after
    a bad id, before the slot (busy or not) and with no model call; the slot stays free."""
    f = Folder(tmp_path)
    slot = JobSlot()
    provider = FakeProvider([])
    people = f.service(provider, slot=slot, recording_busy=lambda: True)
    assert people.write_brief(5) == {"ok": False, "reason": "invalid"}
    assert people.write_brief(f.priya.id) == {"ok": False, "reason": "recording"}
    assert slot.take()  # a question being answered meanwhile: "recording" still, not "busy"
    assert people.write_brief(f.priya.id) == {"ok": False, "reason": "recording"}
    slot.release()
    assert provider.calls == [] and f.events == []
    heard: list[object] = []
    asker = f.asker(FakeProvider([NOT_FOUND]), slot, heard)
    assert asker.ask(f.latest, "What did I promise?")["ok"] is True  # the slot was left free
    wait_for(heard)


def test_a_brief_waits_for_the_note(tmp_path: Path) -> None:
    """RC11: while a note is being written, a brief is refused as a question is: after a
    recording, before the slot (busy or not) and with no model call; the slot stays free."""
    f = Folder(tmp_path)
    slot = JobSlot()
    provider = FakeProvider([])
    people = f.service(provider, slot=slot, note_busy=lambda: True)
    assert people.write_brief(5) == {"ok": False, "reason": "invalid"}
    assert people.write_brief(f.priya.id) == {"ok": False, "reason": "note"}
    assert slot.take()  # a question being answered meanwhile: "note" still, not "busy"
    assert people.write_brief(f.priya.id) == {"ok": False, "reason": "note"}
    slot.release()
    both = f.service(provider, slot=slot, recording_busy=lambda: True, note_busy=lambda: True)
    assert both.write_brief(f.priya.id) == {"ok": False, "reason": "recording"}
    assert provider.calls == [] and f.events == []
    heard: list[object] = []
    asker = f.asker(FakeProvider([NOT_FOUND]), slot, heard)
    assert asker.ask(f.latest, "What did I promise?")["ok"] is True  # the slot was left free
    wait_for(heard)


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
    wait_for(heard)
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
