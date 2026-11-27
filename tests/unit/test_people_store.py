"""People the owner names (BUILD.md §6.5, D14; Plan C Task 1)."""

import sqlite3
from pathlib import Path

import pytest

from evra.services.views import meeting_detail
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.people import MAX_NAME, NameRefused, Person, PersonStore, clean_name
from evra.store.speakers import SpeakerStore


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _meeting(conn: sqlite3.Connection) -> str:
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="Weekly 1:1", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
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
    return mid


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("  Priya   Shah ", "Priya Shah"),
        ("Priya\tShah\n", "Priya Shah"),
        ("", None),
        ("   ", None),
        ("x" * MAX_NAME, "x" * MAX_NAME),
        ("x" * (MAX_NAME + 1), None),
    ],
)
def test_names_are_tidied_and_bounded(given: str, expected: str | None) -> None:
    assert MAX_NAME == 80
    assert clean_name(given) == expected


def test_names_match_case_and_space(conn: sqlite3.Connection) -> None:
    """Review focus 1: two spellings of one person resolve to one person, kept as first typed."""
    people = PersonStore(conn)
    first = people.find_or_create("priya")
    assert first == Person(first.id, "priya")
    assert people.find_or_create("Priya ") == first
    assert people.find_or_create("  PRIYA") == first
    other = people.find_or_create("Priya  Shah")
    assert other.name == "Priya Shah" and other.id != first.id
    assert people.find_or_create("priya shah") == other
    assert people.list_people() == [first, other]


def test_people_are_listed_by_name_without_the_owner(conn: sqlite3.Connection) -> None:
    SpeakerStore(conn).one_on_one(_meeting(conn))  # makes the owner's person, "You"
    people = PersonStore(conn)
    sam, ana, bea = (people.find_or_create(n) for n in ("Sam", "ana", "Bea"))
    assert people.list_people() == [ana, bea, sam]  # by name, whatever its case


def test_rename_to_a_taken_name(conn: sqlite3.Connection) -> None:
    """Review focus 1: a name another person has is refused with a reason."""
    people = PersonStore(conn)
    priya, sam = people.find_or_create("Priya"), people.find_or_create("Sam")
    assert people.rename(sam.id, " priya ") == "taken"
    assert people.rename(sam.id, "PRIYA") == "taken"
    assert people.list_people() == [priya, sam]  # nothing changed
    assert people.rename(priya.id, "  priya  ") == "ok"  # their own name in another case
    assert people.rename(sam.id, "Sam  Lee") == "ok"
    assert people.list_people() == [Person(priya.id, "priya"), Person(sam.id, "Sam Lee")]
    assert people.rename(sam.id, "   ") == "invalid"
    assert people.rename(sam.id, "x" * (MAX_NAME + 1)) == "invalid"
    assert people.rename("nobody", "Dana") == "unknown"


def test_you_is_reserved(conn: sqlite3.Connection) -> None:
    """C2: "You" is the owner's own person, ignoring case and spaces; no one else gets it."""
    speakers = SpeakerStore(conn)
    speakers.one_on_one(_meeting(conn))
    owner = conn.execute("SELECT id FROM person WHERE is_owner = 1").fetchone()["id"]
    people = PersonStore(conn)
    for name in ("You", "you", " YOU ", "Y o u"):
        with pytest.raises(NameRefused) as refused:
            people.find_or_create(name)
        assert refused.value.reason == "reserved"
    with pytest.raises(NameRefused) as invalid:
        people.find_or_create("  ")
    assert invalid.value.reason == "invalid"
    priya = people.find_or_create("Priya")
    assert people.rename(priya.id, " you") == "reserved"
    assert people.rename(owner, "Priya Shah") == "unknown"  # the owner is not one of the people
    assert people.remove(owner) is False
    assert people.list_people() == [priya]
    assert conn.execute("SELECT COUNT(*) FROM person").fetchone()[0] == 2  # the owner and Priya
    assert people.find_or_create("Yours") != priya  # only the word itself is reserved


def test_remove_person_unlinks(conn: sqlite3.Connection) -> None:
    """Review focus 2 (RC1): removing a person unlinks their meetings, which say "Them" again,
    and deletes the person; nothing else goes."""
    mid, other = _meeting(conn), _meeting(conn)
    people, speakers = PersonStore(conn), SpeakerStore(conn)
    priya, sam = people.find_or_create("Priya"), people.find_or_create("Sam")
    speakers.set_person(mid, priya.id)
    speakers.set_person(other, sam.id)
    detail = meeting_detail(conn, mid)
    assert detail is not None and detail["utterances"][0]["speaker"] == "Priya"
    assert people.remove(priya.id) is True
    assert people.list_people() == [sam]
    assert speakers.person_for(mid) is None
    detail = meeting_detail(conn, mid)
    assert detail is not None and detail["with"] is None
    assert [u["speaker"] for u in detail["utterances"]] == ["Them", "You"]
    assert speakers.person_for(other) == sam  # another person's meetings keep them
    assert conn.execute("SELECT COUNT(*) FROM speaker").fetchone()[0] == 4  # rows stay
    assert people.remove(priya.id) is False  # already gone
