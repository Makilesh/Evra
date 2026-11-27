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
from evra.store.people import PersonStore
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


def _call(
    conn: sqlite3.Connection, title: str, started_at: int, starts: Sequence[int]
) -> tuple[str, str, list[str]]:
    """A 1:1 whose transcript has a line starting at each of `starts` (ms into the call)."""
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title=title,
        mode="one_on_one",
        situation="call_headphones",
        template="one_on_one",
        started_at_ms=started_at,
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    lines = [
        store.add_utterance(
            version_id=vid, meeting_id=mid, channel=1, start_ms=s, end_ms=s + 1_000, text="words"
        ).id
        for s in starts
    ]
    return mid, vid, lines


def test_open_promises_by_direction(conn: sqlite3.Connection) -> None:
    """Every open task the owner or the other person took on, newest meeting first, in the order
    found, with the first transcript line it cites. A task with no owner is no one's promise, and
    a decision is not a task."""
    older, older_version, (a1, a2) = _call(conn, "Weekly 1:1", 1_000_000, [5_000, 9_000])
    newer, newer_version, (b1,) = _call(conn, "Design sync", 2_000_000, [3_000])
    first = _save(
        conn,
        older,
        older_version,
        [
            action("Send the vendor quote", ["user", a2, a1]),  # the owner's notes are no line
            CheckedItem("action_item", "Check the travel policy", (a1,), "Them", "next week", 0.9),
            action("Book a room", [a1], owner=None),
            CheckedItem("decision", "Go with the annual plan.", (a1,), "You", None, None),
        ],
    )
    second = _save(
        conn,
        newer,
        newer_version,
        [
            action("Tell marketing about October 14", ["gone"], owner="Them"),
            action("Send it", [b1]),
        ],
    )
    priya = PersonStore(conn).find_or_create("Priya")
    SpeakerStore(conn).set_person(newer, priya.id)
    items = ItemStore(conn)
    marketing, deck = items.for_generation(second)
    quote, travel, _, _ = items.for_generation(first)
    promised = items.open_promises()
    assert [(p.id, p.text, p.owner, p.due) for p in promised] == [
        (marketing.id, "Tell marketing about October 14", "Them", None),
        (deck.id, "Send it", "You", None),
        (quote.id, "Send the vendor quote", "You", None),
        (travel.id, "Check the travel policy", "Them", "next week"),
    ]
    assert [(p.meeting_id, p.meeting_title, p.started_at, p.person) for p in promised] == [
        (newer, "Design sync", 2_000_000, priya),
        (newer, "Design sync", 2_000_000, priya),
        (older, "Weekly 1:1", 1_000_000, None),
        (older, "Weekly 1:1", 1_000_000, None),
    ]
    assert [(p.utterance_id, p.start_ms) for p in promised] == [
        (None, None),  # it cites no line the transcript has
        (b1, 3_000),
        (a2, 9_000),
        (a1, 5_000),
    ]


def test_only_current_generation_items(conn: sqlite3.Connection) -> None:
    """A rewritten note replaces its meeting's promises: none come twice from the older note."""
    mid, vid, (u1, u2) = _call(conn, "Weekly 1:1", 1_000_000, [5_000, 9_000])
    _save(conn, mid, vid, [action("Send the vendor quote", [u1]), action("Book the venue", [u2])])
    rewrite = [action("Send the vendor quote", [u1]), action("Write the postmortem", [u2], "Them")]
    second = _save(conn, mid, vid, rewrite)
    current = ItemStore(conn).for_generation(second)
    assert [(p.id, p.text) for p in ItemStore(conn).open_promises()] == [
        (i.id, i.text) for i in current
    ]


def test_done_and_dismissed_are_left_out(conn: sqlite3.Connection) -> None:
    """A promise ticked done, or found not to be one, leaves the list; opened again, it is back."""
    mid, vid, (u1,) = _call(conn, "Weekly 1:1", 1_000_000, [5_000])
    tasks = [
        action("Send the quote", [u1]),
        action("Book it", [u1]),
        action("Fix it", [u1], "Them"),
    ]
    generation = _save(conn, mid, vid, tasks)
    items = ItemStore(conn)
    quote, venue, _ = items.for_generation(generation)
    assert items.set_status(quote.id, "done") and items.set_status(venue.id, "dismissed")
    assert [p.text for p in items.open_promises()] == ["Fix it"]
    assert items.set_status(quote.id, "open")
    assert [p.text for p in items.open_promises()] == ["Send the quote", "Fix it"]
