import sqlite3
from pathlib import Path

import pytest

from evra.notes.validate import CheckedBullet, CheckedNote
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _meeting(store: MeetingStore, title: str, started: int) -> str:
    return store.create_meeting(
        title=title,
        mode="one_on_one",
        situation="call_headphones",
        template="one_on_one",
        started_at_ms=started,
    )


def test_meetings_are_listed_newest_first_with_a_note_flag(conn: sqlite3.Connection) -> None:
    store = MeetingStore(conn)
    old = _meeting(store, "Old", 1_000)
    new = _meeting(store, "New", 2_000)
    version = store.create_transcript_version(old, kind="live", model="fake")
    note = CheckedNote((CheckedBullet("Done.", ("u",)),), (), 1, 0, {})
    NoteStore(conn).save_generation(
        meeting_id=old,
        transcript_version_id=version,
        note=note,
        provider="fake",
        model="fake",
        prompt_version="a1-v1",
        template="one_on_one",
        tokens_in=1,
        tokens_out=1,
    )
    rows = store.list_meetings()
    assert [(r["id"], r["title"], bool(r["has_note"])) for r in rows] == [
        (new, "New", False),
        (old, "Old", True),
    ]


def test_rename_reports_whether_the_meeting_exists(conn: sqlite3.Connection) -> None:
    store = MeetingStore(conn)
    mid = _meeting(store, "Recording", 1_000)
    assert store.rename_meeting(mid, "Sync with Priya") is True
    assert store.get_meeting(mid)["title"] == "Sync with Priya"
    assert store.rename_meeting("nope", "x") is False


def test_meetings_left_mid_way_by_a_closed_app_are_recovered(conn: sqlite3.Connection) -> None:
    store = MeetingStore(conn)
    recording = _meeting(store, "a", 1_000)
    processing = _meeting(store, "b", 2_000)
    store.finish_meeting(processing, state="processing")
    done = _meeting(store, "c", 3_000)
    store.finish_meeting(done)
    assert store.recover_after_restart() == 2
    assert store.get_meeting(recording)["state"] == "failed"
    assert store.get_meeting(recording)["ended_at"] is not None
    assert store.get_meeting(processing)["state"] == "ready"
    assert store.get_meeting(done)["state"] == "ready"
