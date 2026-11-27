"""A person's prep brief (Plan C, A13): one kept per person, the newest; forgetting the person
deletes it through the schema (RC1), and nothing else."""

import sqlite3
from pathlib import Path

import pytest

from evra.notes.brief import BriefResult, BriefSource
from evra.notes.validate import CheckedBullet, CheckedNote
from evra.store.briefs import BriefPoint, BriefStore
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore
from evra.store.people import Person, PersonStore
from evra.store.speakers import SpeakerStore


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _meeting(conn: sqlite3.Connection, person: Person, title: str) -> str:
    """A 1:1 with the person, with a transcript and a note."""
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title=title, mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    line = store.add_utterance(
        version_id=vid, meeting_id=mid, channel=1, start_ms=0, end_ms=3_000, text="Hello."
    )
    note = CheckedNote((CheckedBullet("They said hello.", (line.id,)),), (), 1, 0, {})
    NoteStore(conn).save_generation(
        meeting_id=mid,
        transcript_version_id=vid,
        note=note,
        provider="fake",
        model="fake:1b",
        prompt_version="a0-v1+a1-v4",
        template="one_on_one",
        tokens_in=1,
        tokens_out=1,
    )
    SpeakerStore(conn).set_person(mid, person.id)
    return mid


def _result(
    points: list[tuple[str, tuple[str, ...]]], meetings: list[str], version: str = "a13-v1"
) -> BriefResult:
    sources = tuple(
        BriefSource(f"m:{n}", mid, "t", n, "- x") for n, mid in enumerate(meetings, start=1)
    )
    return BriefResult(
        state="written",
        points=tuple(CheckedBullet(text, cites) for text, cites in points),
        sources=sources,
        model="fake:1b",
        prompt_version=version,
        seconds=1.5,
    )


def test_brief_saved_and_replaced(conn: sqlite3.Connection) -> None:
    people = PersonStore(conn)
    priya, sam = people.find_or_create("Priya"), people.find_or_create("Sam")
    latest, earlier = _meeting(conn, priya, "Weekly 1:1"), _meeting(conn, priya, "Budget")
    briefs = BriefStore(conn)
    assert briefs.latest(priya.id) is None
    first = briefs.save(
        priya.id,
        _result(
            [("Send the proposal.", ("m:1",)), ("The budget is set.", ("m:2", "m:1"))],
            [latest, earlier],
        ),
    )
    assert first is not None
    assert first.person_id == priya.id
    assert first.points == (
        BriefPoint("Send the proposal.", (latest,)),  # each m:<n> is the meeting it stood for
        BriefPoint("The budget is set.", (earlier, latest)),
    )
    assert first.meetings == (latest, earlier)  # what it was written from, newest first
    assert (first.model, first.prompt_version) == ("fake:1b", "a13-v1")
    assert briefs.latest(priya.id) == first
    assert briefs.latest(sam.id) is None  # each person has their own

    again = briefs.save(priya.id, _result([("Ask about the offsite.", ("m:1",))], [latest]))
    assert again is not None and again.id != first.id
    assert briefs.latest(priya.id) == again  # the newer brief replaces the one before
    count = conn.execute("SELECT count(*) FROM brief WHERE person_id = ?", (priya.id,))
    assert count.fetchone()[0] == 1
    assert briefs.save("nobody", _result([("x.", ("m:1",))], [latest])) is None


def test_remove_person_deletes_briefs(conn: sqlite3.Connection) -> None:
    """D14 and RC1: forgetting a person deletes their briefs (the schema cascades); their
    meetings and the meetings' notes stay, saying "Them" again."""
    people = PersonStore(conn)
    priya, sam = people.find_or_create("Priya"), people.find_or_create("Sam")
    mid = _meeting(conn, priya, "Weekly 1:1")
    other = _meeting(conn, sam, "Hiring sync")
    briefs = BriefStore(conn)
    briefs.save(priya.id, _result([("Send the proposal.", ("m:1",))], [mid]))
    kept = briefs.save(sam.id, _result([("Book the room.", ("m:1",))], [other]))
    assert people.remove(priya.id) is True
    assert briefs.latest(priya.id) is None
    count = conn.execute("SELECT count(*) FROM brief WHERE person_id = ?", (priya.id,))
    assert count.fetchone()[0] == 0
    assert briefs.latest(sam.id) == kept  # someone else's brief stays
    assert MeetingStore(conn).get_meeting(mid)["title"] == "Weekly 1:1"
    note = NoteStore(conn).current_note(mid)
    assert note is not None and [b.text for b in note.blocks] == ["They said hello."]
    assert SpeakerStore(conn).person_for(mid) is None
