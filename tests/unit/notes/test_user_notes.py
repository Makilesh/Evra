"""The owner's typed notes in every prompt about a meeting (BUILD.md §7.4; RB1, RB46)."""

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from evra.config import LlmSettings
from evra.notes.ask import ask_meeting
from evra.notes.context import ELLIPSIS, LOOKALIKE_GT, LOOKALIKE_LT, NONE
from evra.notes.errors import NoTranscript
from evra.notes.job import write_and_save
from evra.notes.templates import load_template
from evra.notes.title import name_meeting
from evra.notes.user_notes import (
    NotesInput,
    format_user_notes,
    meeting_context,
    notes_input,
    notes_text,
)
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notepad import LineIn, NoteLine, NotepadStore, Phase
from tests.unit.notes.fakes import FakeProvider, title_reply

ALIASES = {"u:1": "a", "u:2": "b", "u:3": "c"}
PLACEHOLDER = "Recording 2026-11-27 10:00"
NO_ITEMS = json.dumps({"items": []})


def nl(
    line_id: str,
    position: int,
    text: str,
    at_ms: int | None,
    phase: Phase = "during",
    *,
    context: bool = False,
    aligned: Sequence[tuple[str, float]] = (),
) -> NoteLine:
    return NoteLine(line_id, position, text, at_ms, phase, context, tuple(aligned))


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def test_format_user_notes() -> None:
    pasted = "Pasted spec " * 50
    lines = [
        nl("z", 2, "Agenda: budget, hiring", -30_000, "before"),
        nl("x", 0, "Budget approved!", 12_000, aligned=[("b", 0.5), ("a", 0.9)]),
        nl("y", 1, "Dana\n14th <ask HR>", 70_000),
        nl("w", 3, "Send recap", 4_000_000, "after"),
        nl("v", 4, pasted, 20_000, context=True),
        nl("gone", 5, "Old link", 15_000, aligned=[("not-in-transcript", 0.7)]),
    ]
    assert format_user_notes(lines, ALIASES).splitlines() == [
        "[n:1] (00:12) Budget approved! || aligned: u:1, u:2",  # in the call's order
        f"[n:2] (01:10) Dana 14th {LOOKALIKE_LT}ask HR{LOOKALIKE_GT}",  # inert, on one line
        "[n:3] (before) Agenda: budget, hiring",
        "[n:4] (after) Send recap",
        f"[n:5] (context) {pasted.strip()}",
        "[n:6] (00:15) Old link",
    ]
    assert format_user_notes([], ALIASES) == NONE
    # a part of a long call shows some of the notes, numbered as the whole meeting numbers them
    assert format_user_notes(lines, ALIASES, only={"z", "gone"}).splitlines() == [
        "[n:3] (before) Agenda: budget, hiring",
        "[n:6] (00:15) Old link",
    ]
    assert format_user_notes(lines, ALIASES, only=set()) == NONE


def test_notes_text_is_what_a_user_citation_is_checked_against() -> None:
    lines = [nl("b", 1, "Dana starts the 14th", 9_000), nl("a", 0, "Budget approved", 5_000)]
    assert notes_text(lines) == "Budget approved\nDana starts the 14th"
    assert notes_text([]) == ""
    assert notes_input(lines) == NotesInput((lines[1], lines[0]), notes_text(lines))


def _meeting(conn: sqlite3.Connection, title: str = PLACEHOLDER) -> str:
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title=title, mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    for channel, start_ms, text in [
        (1, 0, "Finance approved the budget for the beta."),
        (0, 5_000, "Great, then Dana starts on the 14th."),
    ]:
        store.add_utterance(
            version_id=vid,
            meeting_id=mid,
            channel=channel,
            start_ms=start_ms,
            end_ms=start_ms + 4_000,
            text=text,
        )
    started = int(store.get_meeting(mid)["started_at"])
    NotepadStore(conn).replace(mid, [LineIn("n1", "Budget approved", started + 12_000, False)])
    return mid


def test_meeting_context_reads_the_stored_notes_and_their_links(conn: sqlite3.Connection) -> None:
    mid = _meeting(conn)
    store = MeetingStore(conn)
    version = store.current_transcript_version(mid)
    assert version is not None
    first = store.utterances(version)[0]
    NotepadStore(conn).set_alignment(mid, {"n1": [(first.id, 0.8)]})
    context, notes = meeting_context(conn, mid)
    assert "<user_notes>\n[n:1] (00:12) Budget approved || aligned: u:1\n</user_notes>" in (
        context.system
    )
    assert "[u:2] [00:05] You: Great, then Dana starts on the 14th." in context.system
    assert notes.user_notes == "Budget approved" and [n.id for n in notes.lines] == ["n1"]
    bare, _ = meeting_context(conn, mid, only=(), note="No lines here.\n")
    lines = bare.system.split("<transcript>\n", 1)[1].split("\n</transcript>", 1)[0]
    assert lines == "No lines here.\n" + ELLIPSIS
    assert "[n:1] (00:12) Budget approved || aligned: u:1" in bare.system  # the notes stay
    with pytest.raises(KeyError):
        meeting_context(conn, "no-such-meeting")
    empty = MeetingStore(conn).create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    with pytest.raises(NoTranscript):
        meeting_context(conn, empty)


def test_the_note_its_title_and_questions_share_one_context(conn: sqlite3.Connection) -> None:
    """RB1: the note job, the title (A8) and asking send the same system message for one
    meeting (the title, renamed by A8, is the only part that differs afterwards)."""
    mid = _meeting(conn)
    store = MeetingStore(conn)
    version = store.current_transcript_version(mid)
    assert version is not None
    point = {"text": "Budget approved.", "citations": ["user"]}
    reply = json.dumps({"summary": [point], "sections": []})
    writer = FakeProvider([reply, NO_ITEMS, NO_ITEMS, NO_ITEMS])
    write_and_save(
        conn,
        meeting=store.get_meeting(mid),
        version_id=version,
        utterances=store.utterances(version),
        template=load_template("one_on_one"),
        provider=writer,
        model="fake:1b",
        settings=LlmSettings(),
    )
    note_system = writer.calls[0][0].content
    assert "[n:1] (00:12) Budget approved || aligned: u:" in note_system
    assert len({call[0].content for call in writer.calls}) == 1  # A1 and A4-A6
    titler = FakeProvider([title_reply("Budget and Dana")])
    assert name_meeting(conn, mid, provider=titler, model="fake:1b") == "Budget and Dana"
    assert titler.calls[0][0].content == note_system
    context, notes = meeting_context(conn, mid)
    asker = FakeProvider([json.dumps({"found": False, "points": []})])
    ask_meeting(
        asker,
        model="fake:1b",
        meeting=store.get_meeting(mid),
        utterances=store.utterances(version),
        question="When does Dana start?",
        settings=LlmSettings(),
        notes=notes,
        context=context,
    )
    renamed = note_system.replace(f"title: {PLACEHOLDER}", "title: Budget and Dana")
    assert renamed != note_system
    assert asker.calls[0][0].content == renamed
