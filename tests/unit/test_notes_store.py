import sqlite3
from pathlib import Path

import pytest

from evra.notes.validate import CheckedBullet, CheckedNote, CheckedSection
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import SUMMARY, NoteStore


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _meeting(conn: sqlite3.Connection, started: int = 1_000) -> tuple[str, str]:
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="t",
        mode="one_on_one",
        situation="call_headphones",
        template="one_on_one",
        started_at_ms=started,
    )
    return mid, store.create_transcript_version(mid, kind="live", model="fake")


NOTE = CheckedNote(
    summary=(CheckedBullet("Migration done.", ("u1",)),),
    sections=(
        CheckedSection(
            "action_items",
            "Action items",
            (
                CheckedBullet("Send the proposal.", ("u2", "u3")),
                CheckedBullet("Ask Priya.", ("u4",)),
            ),
        ),
    ),
    kept=3,
    dropped=2,
    drop_reasons={"unsupported": 2},
)


def _save(notes: NoteStore, mid: str, vid: str, model: str = "gemma4:12b") -> str:
    return notes.save_generation(
        meeting_id=mid,
        transcript_version_id=vid,
        note=NOTE,
        provider="ollama",
        model=model,
        prompt_version="a1-v1",
        template="one_on_one",
        tokens_in=1200,
        tokens_out=300,
    )


def test_meeting_helpers(conn: sqlite3.Connection) -> None:
    store = MeetingStore(conn)
    assert store.latest_meeting_id() is None
    first, _ = _meeting(conn, started=1_000)
    second, version = _meeting(conn, started=2_000)
    assert store.latest_meeting_id() == second
    assert store.current_transcript_version(second) == version
    assert store.current_transcript_version("nope") is None
    assert first != second


def test_saved_note_reads_back_in_order(conn: sqlite3.Connection) -> None:
    mid, vid = _meeting(conn)
    notes = NoteStore(conn)
    generation = _save(notes, mid, vid)
    stored = notes.current_note(mid)
    assert stored is not None
    assert (stored.generation_id, stored.model, stored.dropped_claims) == (
        generation,
        "gemma4:12b",
        2,
    )
    assert [(b.section, b.position, b.text, b.citations, b.provenance) for b in stored.blocks] == [
        (SUMMARY, 0, "Migration done.", ("u1",), "generated"),
        ("action_items", 1, "Send the proposal.", ("u2", "u3"), "generated"),
        ("action_items", 2, "Ask Priya.", ("u4",), "generated"),
    ]
    row = conn.execute("SELECT * FROM generation WHERE id = ?", (generation,)).fetchone()
    assert (row["tokens_in"], row["tokens_out"], row["llm_provider"]) == (1200, 300, "ollama")


def test_a_new_generation_becomes_current(conn: sqlite3.Connection) -> None:
    mid, vid = _meeting(conn)
    notes = NoteStore(conn)
    first = _save(notes, mid, vid, model="a")
    second = _save(notes, mid, vid, model="b")
    stored = notes.current_note(mid)
    assert stored is not None and stored.generation_id == second != first
    currents = conn.execute(
        "SELECT COUNT(*) FROM generation WHERE meeting_id = ? AND is_current = 1", (mid,)
    ).fetchone()[0]
    assert currents == 1


def test_no_note_yet(conn: sqlite3.Connection) -> None:
    mid, _ = _meeting(conn)
    assert NoteStore(conn).current_note(mid) is None


def test_deleting_the_meeting_removes_its_notes(conn: sqlite3.Connection) -> None:
    mid, vid = _meeting(conn)
    _save(NoteStore(conn), mid, vid)
    conn.execute("DELETE FROM meeting WHERE id = ?", (mid,))
    assert conn.execute("SELECT COUNT(*) FROM generation").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM output_block").fetchone()[0] == 0
