"""The Promises page's bridge (Plan C): every open promise across the 1:1s, and the event that
tells the window to read them again. Beside test_bridge.py, whose helpers it shares."""

import json
from pathlib import Path

import structlog

from evra.bridge.events import EventBus, build_emit_script
from evra.notes.extract import CheckedItem
from evra.notes.validate import CheckedNote
from evra.store.db import connect
from evra.store.items import ItemStore
from evra.store.meetings import MeetingStore
from evra.store.notes import NoteStore
from tests.unit.test_bridge import FakeWindow, _api, _meeting

CHANGED = build_emit_script("promises.changed", {})


def _note(db: Path, meeting_id: str) -> tuple[str, str, str]:
    """A note on the meeting with a task for each side, both citing its one transcript line:
    that line's id, then the two tasks' ids."""
    conn = connect(db)
    try:
        store = MeetingStore(conn)
        vid = store.create_transcript_version(meeting_id, kind="live", model="fake")
        line = store.add_utterance(
            version_id=vid,
            meeting_id=meeting_id,
            channel=1,
            start_ms=65_000,
            end_ms=70_000,
            text="x",
        )
        generation = NoteStore(conn).save_generation(
            meeting_id=meeting_id,
            transcript_version_id=vid,
            note=CheckedNote((), (), 0, 0, {}),
            provider="fake",
            model="fake:1b",
            prompt_version="a0-v1+a4-v2",
            template="one_on_one",
            tokens_in=1,
            tokens_out=1,
            items=[
                CheckedItem("action_item", "Send the quote", (line.id,), "You", "by Friday", 0.9),
                CheckedItem("action_item", "Tell marketing", ("user", line.id), "Them", None, 0.9),
            ],
        )
        quote, marketing = ItemStore(conn).for_generation(generation)
        return line.id, quote.id, marketing.id
    finally:
        conn.close()


def test_open_promises_are_listed_by_direction_as_json(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid = _meeting(db)
    line, quote, marketing = _note(db, mid)
    priya = api.set_meeting_person(mid, "Priya")["with"]
    with structlog.testing.capture_logs() as logs:
        listed = api.list_promises()
    json.dumps(listed)
    shared = {
        "meeting_id": mid,
        "meeting_title": "Weekly 1:1",
        "started_at": api.list_meetings()[0]["started_at"],
        "person": priya,
        "utterance_id": line,
        "start_ms": 65_000,
    }
    assert listed == {
        "you": [
            {"id": quote, "text": "Send the quote", "due": "by Friday", "owner": "You", **shared}
        ],
        "them": [
            {"id": marketing, "text": "Tell marketing", "due": None, "owner": "Them", **shared}
        ],
    }
    assert logs == []  # a promise, its meeting and its person are content
    assert api.set_meeting_person(mid, None)["ok"] is True
    assert [p["person"] for p in api.list_promises()["them"]] == [None]  # shown as "Them"


def test_the_window_hears_when_promises_change(tmp_path: Path) -> None:
    """A saved status, and who a 1:1 was with, change what the Promises page shows, so the window
    is told to read it again. A refused call changes nothing and says nothing."""
    bus, window = EventBus(), FakeWindow()
    bus.attach(window)
    api, db = _api(tmp_path, bus=bus)
    mid = _meeting(db)
    _, quote, _ = _note(db, mid)
    for item_id, status in [(quote, "finished"), ("nope", "done"), (5, "done"), (quote, None)]:
        assert api.set_item_status(item_id, status) == {"ok": False}  # type: ignore[arg-type]
    assert api.set_meeting_person(mid, "You")["ok"] is False
    assert window.scripts == []
    assert api.set_item_status(quote, "done") == {"ok": True}
    assert window.scripts == [CHANGED]
    assert api.set_meeting_person(mid, "Priya")["ok"] is True
    assert api.set_meeting_person(mid, "")["ok"] is True
    assert window.scripts == [CHANGED] * 3
