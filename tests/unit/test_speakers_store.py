import sqlite3
from pathlib import Path

import pytest

from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.speakers import SpeakerStore


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _meeting(conn: sqlite3.Connection) -> str:
    return MeetingStore(conn).create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )


def test_speakers_created_once(conn: sqlite3.Connection) -> None:
    first, second = _meeting(conn), _meeting(conn)
    speakers = SpeakerStore(conn)
    pair = speakers.one_on_one(first)
    assert speakers.one_on_one(first) == pair  # the same rows on every later use
    other = speakers.one_on_one(second)
    assert len({pair.you, pair.them, other.you, other.them}) == 4
    owners = conn.execute("SELECT id, display_name FROM person WHERE is_owner = 1").fetchall()
    assert [r["display_name"] for r in owners] == ["You"]  # one owner for the whole database
    owner = owners[0]["id"]
    rows = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM speaker").fetchall()}
    assert len(rows) == 4
    fields = ("meeting_id", "namespace", "label", "person_id", "source")
    assert tuple(rows[pair.you][f] for f in fields) == (first, "room", "You", owner, "mode")
    assert tuple(rows[pair.them][f] for f in fields) == (first, "remote", "Them", None, "mode")
    assert rows[other.you]["person_id"] == owner


def test_speakers_join_the_callers_transaction(conn: sqlite3.Connection) -> None:
    mid = _meeting(conn)
    conn.execute("BEGIN")
    SpeakerStore(conn).one_on_one(mid)
    conn.execute("ROLLBACK")
    assert conn.execute("SELECT COUNT(*) FROM speaker").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM person").fetchone()[0] == 0
