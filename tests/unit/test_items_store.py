import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from evra.notes.extract import CheckedItem
from evra.notes.validate import CheckedBullet, CheckedNote
from evra.store.db import connect
from evra.store.items import ItemStore
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore
from evra.store.speakers import SpeakerStore

NOTE = CheckedNote(
    summary=(CheckedBullet("The quote goes out this week.", ("u1",)),),
    sections=(),
    kept=1,
    dropped=0,
    drop_reasons={},
)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _meeting(conn: sqlite3.Connection) -> tuple[str, str]:
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    return mid, store.create_transcript_version(mid, kind="live", model="fake")


def action(text: str, cites: Sequence[str], owner: str | None = "You") -> CheckedItem:
    return CheckedItem("action_item", text, tuple(cites), owner, None, 0.9)


def _save(conn: sqlite3.Connection, mid: str, vid: str, items: Sequence[CheckedItem]) -> str:
    return NoteStore(conn).save_generation(
        meeting_id=mid,
        transcript_version_id=vid,
        note=NOTE,
        provider="fake",
        model="fake:1b",
        prompt_version="a0-v1+a1-v4+a4-v1+a5-v1+a6-v1",
        template="one_on_one",
        tokens_in=1,
        tokens_out=1,
        items=items,
    )


def test_items_saved_with_the_generation(conn: sqlite3.Connection) -> None:
    mid, vid = _meeting(conn)
    generation = _save(
        conn,
        mid,
        vid,
        [
            CheckedItem(
                "action_item", "Send the vendor quote", ("u1", "u2"), "You", "by Friday", 0.9
            ),
            CheckedItem("decision", "Go with the annual plan.", ("u3",), None, None, None),
            CheckedItem(
                "open_question", "Who owns the review?", ("u4", "user"), "Them", None, None
            ),
        ],
    )
    stored = ItemStore(conn).for_generation(generation)
    assert [(s.kind, s.text, s.owner, s.due, s.citations, s.status) for s in stored] == [
        ("action_item", "Send the vendor quote", "You", "by Friday", ("u1", "u2"), "open"),
        ("decision", "Go with the annual plan.", None, None, ("u3",), "open"),
        ("open_question", "Who owns the review?", "Them", None, ("u4", "user"), "open"),
    ]
    pair = SpeakerStore(conn).one_on_one(mid)
    row = conn.execute("SELECT * FROM action_item").fetchone()
    assert (row["owner_speaker_id"], row["generation_id"], row["meeting_id"]) == (
        pair.you,
        generation,
        mid,
    )
    assert row["confidence"] == 0.9 and row["status_changed_at"] is None
    assert conn.execute("SELECT raised_by_speaker_id FROM open_question").fetchone()[0] == pair.them
    assert conn.execute("SELECT made_by_speaker_id FROM decision").fetchone()[0] is None


def test_a_note_whose_items_cannot_be_saved_is_not_saved(conn: sqlite3.Connection) -> None:
    mid, vid = _meeting(conn)
    unknown = CheckedItem("topic", "Pricing", ("u1",), None, None, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _save(conn, mid, vid, [action("Send the vendor quote", ["u1"]), unknown])
    assert NoteStore(conn).current_note(mid) is None  # one transaction: nothing was kept
    assert conn.execute("SELECT COUNT(*) FROM action_item").fetchone()[0] == 0


def test_status_survives_a_rewrite(conn: sqlite3.Connection) -> None:
    mid, vid = _meeting(conn)
    items = ItemStore(conn)
    first = _save(
        conn,
        mid,
        vid,
        [
            action("Send the vendor quote", ["u1"]),
            action("Book the offsite venue", ["u2"]),
            action("Update the deck", ["u5"]),
            action("Send the deck to Priya", ["u5"]),
        ],
    )
    quote, venue, deck, _ = items.for_generation(first)
    assert items.set_status(quote.id, "done")
    assert items.set_status(venue.id, "dismissed")
    assert items.set_status(deck.id, "done")
    second = _save(
        conn,
        mid,
        vid,
        [
            action("Send the vendor quote", ["u9"]),  # the same words, cited elsewhere
            action("Book the venue for the offsite", ["u2"]),  # reworded, on the same line
            action("Send the deck to Priya", ["u5"]),  # shares only a line with the done deck
            action("Write the postmortem", ["u7"]),  # new
        ],
    )
    assert [(s.text, s.status) for s in items.for_generation(second)] == [
        ("Send the vendor quote", "done"),
        ("Book the venue for the offsite", "dismissed"),
        ("Send the deck to Priya", "open"),
        ("Write the postmortem", "open"),
    ]
    third = _save(conn, mid, vid, [action("Send the vendor quote", ["u1"])])
    assert [s.status for s in items.for_generation(third)] == [
        "done"
    ]  # and on, rewrite after rewrite


def test_set_status_only_known_values(conn: sqlite3.Connection) -> None:
    mid, vid = _meeting(conn)
    decided = CheckedItem("decision", "Go with the annual plan.", ("u3",), None, None, None)
    generation = _save(conn, mid, vid, [action("Send the vendor quote", ["u1"]), decided])
    items = ItemStore(conn)
    quote, decision = items.for_generation(generation)
    for status in ("done", "dismissed", "open"):
        assert items.set_status(quote.id, status) is True
        assert items.for_generation(generation)[0].status == status
    stamped = conn.execute(
        "SELECT status_changed_at FROM action_item WHERE id = ?", (quote.id,)
    ).fetchone()[0]
    assert stamped is not None and stamped > 0
    for bad in ("finished", "", "DONE", "open "):
        assert items.set_status(quote.id, bad) is False
    assert items.for_generation(generation)[0].status == "open"
    assert items.set_status("nope", "done") is False
    assert items.set_status(decision.id, "done") is False  # only action items are ticked
