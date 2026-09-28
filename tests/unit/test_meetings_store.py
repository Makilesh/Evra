from pathlib import Path

import pytest

from evra.asr.engine import Word
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate


@pytest.fixture
def store(tmp_path: Path) -> MeetingStore:
    conn = connect(tmp_path / "evra.db")
    migrate(conn)
    return MeetingStore(conn)


def _meeting(store: MeetingStore) -> str:
    return store.create_meeting(
        title="Sync", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )


def test_meeting_lifecycle(store: MeetingStore) -> None:
    mid = _meeting(store)
    assert store.get_meeting(mid)["state"] == "recording"
    store.finish_meeting(mid)
    row = store.get_meeting(mid)
    assert row["state"] == "ready" and row["ended_at"] is not None


def test_new_transcript_version_becomes_current(store: MeetingStore) -> None:
    mid = _meeting(store)
    v1 = store.create_transcript_version(mid, kind="live", model="parakeet")
    v2 = store.create_transcript_version(mid, kind="fast", model="parakeet")
    rows = store._conn.execute(  # checking the flag directly
        "SELECT id, is_current FROM transcript_version WHERE meeting_id = ?", (mid,)
    ).fetchall()
    assert {r["id"]: r["is_current"] for r in rows} == {v1: 0, v2: 1}


def test_utterances_get_sequence_numbers_and_come_back_in_time_order(store: MeetingStore) -> None:
    mid = _meeting(store)
    vid = store.create_transcript_version(mid, kind="live", model="parakeet")
    store.add_utterance(
        version_id=vid,
        meeting_id=mid,
        channel=1,
        start_ms=5000,
        end_ms=6000,
        text="later",
        words=(Word(5000, 6000, "later"),),
    )
    store.add_utterance(
        version_id=vid, meeting_id=mid, channel=0, start_ms=1000, end_ms=2000, text="earlier"
    )
    got = store.utterances(vid)
    assert [u.text for u in got] == ["earlier", "later"]
    assert sorted(u.seq for u in got) == [0, 1]
    assert got[1].words == (Word(5000, 6000, "later"),)
    assert got[0].words == ()
