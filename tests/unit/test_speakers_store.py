import sqlite3
from pathlib import Path

import pytest

from evra.services.views import meeting_detail
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.people import PersonStore
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


def test_set_person_relabels_the_transcript(conn: sqlite3.Connection) -> None:
    """The other person on the call ("Them") is named once the owner says who it was with;
    saying no one brings "Them" back."""
    store = MeetingStore(conn)
    mid = _meeting(conn)
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    for channel, start_ms, text in [(1, 0, "How was your week?"), (0, 4_000, "Busy, but good.")]:
        store.add_utterance(
            version_id=vid,
            meeting_id=mid,
            channel=channel,
            start_ms=start_ms,
            end_ms=start_ms + 3_000,
            text=text,
        )
    speakers = SpeakerStore(conn)
    assert speakers.person_for(mid) is None
    assert conn.execute("SELECT COUNT(*) FROM speaker").fetchone()[0] == 0  # a read makes none
    priya = PersonStore(conn).find_or_create("Priya")
    speakers.set_person(mid, priya.id)
    assert speakers.person_for(mid) == priya
    pair = speakers.one_on_one(mid)
    linked = conn.execute("SELECT person_id FROM speaker WHERE id = ?", (pair.them,)).fetchone()
    assert linked["person_id"] == priya.id  # the remote speaker of the meeting's pair
    detail = meeting_detail(conn, mid)
    assert detail is not None
    assert [u["speaker"] for u in detail["utterances"]] == ["Priya", "You"]
    assert detail["with"] == {"id": priya.id, "name": "Priya"}
    assert detail["meeting"]["with_name"] == "Priya"
    speakers.set_person(mid, None)
    assert speakers.person_for(mid) is None
    detail = meeting_detail(conn, mid)
    assert detail is not None and detail["with"] is None
    assert [u["speaker"] for u in detail["utterances"]] == ["Them", "You"]
    assert detail["meeting"]["with_name"] is None


def test_set_person_needs_a_meeting_and_a_named_person(conn: sqlite3.Connection) -> None:
    mid = _meeting(conn)
    speakers = SpeakerStore(conn)
    priya = PersonStore(conn).find_or_create("Priya")
    with pytest.raises(KeyError):
        speakers.set_person("no-such-meeting", priya.id)
    with pytest.raises(KeyError):
        speakers.set_person(mid, "no-such-person")
    owner = speakers.one_on_one(mid).you
    owner_person = conn.execute("SELECT person_id FROM speaker WHERE id = ?", (owner,)).fetchone()
    with pytest.raises(KeyError):  # the owner is never the other person on their own call
        speakers.set_person(mid, owner_person["person_id"])
    assert speakers.person_for(mid) is None
