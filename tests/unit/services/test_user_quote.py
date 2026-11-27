"""RB40: the owner's note line a point quotes when it cites their notes ([user])."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from evra.notes.extract import CheckedItem
from evra.notes.validate import CheckedBullet, CheckedNote, shared_words
from evra.services.views import meeting_detail
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notepad import LineIn, NotepadStore
from evra.store.notes import NoteStore

STARTED = 1_790_600_000_000
LINES = [  # (id, text, ms into the call), in the pad's order
    ("a", "designer budget ok", 65_000),
    ("b", "ask Priya about API limits", 125_000),
    ("c", "API limits block the launch", 130_000),
]


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _blocks(
    conn: sqlite3.Connection,
    bullets: list[tuple[str, tuple[str, ...]]],
    items: list[CheckedItem] | None = None,
) -> list[dict[str, Any]]:
    """The note's points as the window gets them: a meeting with two transcript lines (cited
    as "budget" and "api"), the three typed lines, and a linked to budget, b to api."""
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="Weekly 1:1",
        mode="one_on_one",
        situation="call_headphones",
        template="one_on_one",
        started_at_ms=STARTED,
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    budget, api = (
        store.add_utterance(
            version_id=vid, meeting_id=mid, channel=1, start_ms=at, end_ms=at + 4_000, text=text
        ).id
        for at, text in [
            (60_000, "Finance approved the designer budget."),
            (120_000, "We still need the API limits from Priya."),
        ]
    )
    notepad = NotepadStore(conn)
    notepad.replace(mid, [LineIn(i, text, STARTED + at, False) for i, text, at in LINES])
    notepad.set_alignment(mid, {"a": [(budget, 0.8)], "b": [(api, 0.7)]})
    named = {"budget": budget, "api": api}
    note = CheckedNote(
        summary=tuple(
            CheckedBullet(text, tuple(named.get(c, c) for c in cites)) for text, cites in bullets
        ),
        sections=(),
        kept=len(bullets),
        dropped=0,
        drop_reasons={},
    )
    NoteStore(conn).save_generation(
        meeting_id=mid,
        transcript_version_id=vid,
        note=note,
        provider="ollama",
        model="gemma4:12b",
        prompt_version="a0-v1+a1-v4",
        template="one_on_one",
        tokens_in=1,
        tokens_out=1,
        items=items or [],
    )
    detail = meeting_detail(conn, mid)
    assert detail is not None and detail["note"] is not None
    json.dumps(detail)  # it crosses the bridge as JSON
    return [block for section in detail["note"]["sections"] for block in section["blocks"]]


def _quoted(block: dict[str, Any]) -> str | None:
    quote = block.get("user_quote")
    return None if quote is None else str(quote["id"])


def test_a_point_quotes_the_line_linked_to_what_it_cites(conn: sqlite3.Connection) -> None:
    [linked, two_linked] = _blocks(
        conn,
        [
            # c shares more words, but a is the line linked to the budget line it cites
            ("Finance approved the budget for API limits.", ("budget", "user")),
            # both a and b are linked to what it cites: b shares its words
            ("Priya will send the API limits.", ("budget", "api", "user")),
        ],
    )
    assert linked["user_quote"] == {"id": "a", "text": "designer budget ok"}
    assert _quoted(two_linked) == "b"
    assert [c["start_ms"] for c in linked["citations"]] == [60_000]  # "user" is no time


def test_otherwise_the_line_sharing_the_most_words_earlier_on_a_tie(
    conn: sqlite3.Connection,
) -> None:
    most, tie, none, not_cited = _blocks(
        conn,
        [
            ("The launch is blocked by API limits.", ("user",)),  # c: 4 words, b: 2
            ("API limits matter.", ("user",)),  # b and c share 2 each: the earlier
            ("Everyone was happy.", ("user",)),  # kept by its meaning alone: no line
            ("Finance approved the designer budget.", ("budget",)),  # cites no notes
        ],
    )
    assert (_quoted(most), _quoted(tie)) == ("c", "b")
    assert "user_quote" not in none and "user_quote" not in not_cited


def test_an_item_from_your_notes_quotes_its_line(conn: sqlite3.Connection) -> None:
    item = CheckedItem("action_item", "Ask Priya about the API limits", ("user",), "You", None, 0.9)
    [block] = _blocks(conn, [], items=[item])
    assert block["text"] == "You: Ask Priya about the API limits"  # the point as shown
    assert block["item"]["kind"] == "action_item"
    assert block["user_quote"] == {"id": "b", "text": "ask Priya about API limits"}


def test_shared_words_is_the_word_checks_measure() -> None:
    # content words by their first five letters; stopwords and digits don't count
    assert shared_words("The launch is blocked by API limits.", "API limits block the launch") == 4
    assert shared_words("Budgets were approved", "budget approval") == 2
    assert shared_words("It is what it is", "it is what it is") == 0
