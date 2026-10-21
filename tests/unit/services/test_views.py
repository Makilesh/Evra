import json
import sqlite3
from pathlib import Path

import pytest

from evra.notes.validate import CheckedBullet, CheckedNote, CheckedSection
from evra.services.views import clean_title, meeting_detail, meeting_summary
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def test_detail_has_labelled_lines_and_note_sections_with_citation_times(
    conn: sqlite3.Connection,
) -> None:
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="Weekly 1:1", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    them = store.add_utterance(
        version_id=vid,
        meeting_id=mid,
        channel=1,
        start_ms=65_000,
        end_ms=70_000,
        text="Marketing wants October 14.",
    )
    you = store.add_utterance(
        version_id=vid,
        meeting_id=mid,
        channel=0,
        start_ms=110_000,
        end_ms=114_000,
        text="I'll send the proposal by Thursday.",
    )
    note = CheckedNote(
        summary=(CheckedBullet("Launch moves to October 14.", (them.id,)),),
        sections=(
            CheckedSection(
                "action_items",
                "Action items",
                (CheckedBullet("You: send the proposal.", (you.id, "gone")),),
            ),
        ),
        kept=2,
        dropped=0,
        drop_reasons={},
    )
    NoteStore(conn).save_generation(
        meeting_id=mid,
        transcript_version_id=vid,
        note=note,
        provider="ollama",
        model="gemma4:12b",
        prompt_version="a1-v1",
        template="one_on_one",
        tokens_in=1,
        tokens_out=1,
    )
    detail = meeting_detail(conn, mid)
    assert detail is not None
    assert detail["meeting"]["has_note"] is True
    assert [(u["speaker"], u["text"]) for u in detail["utterances"]] == [
        ("Them", "Marketing wants October 14."),
        ("You", "I'll send the proposal by Thursday."),
    ]
    assert detail["note"] == {
        "model": "gemma4:12b",
        "sections": [
            {
                "id": "summary",
                "title": "Summary",
                "blocks": [
                    {
                        "text": "Launch moves to October 14.",
                        "citations": [{"utterance_id": them.id, "start_ms": 65_000}],
                    }
                ],
            },
            {
                "id": "action_items",
                "title": "Action items",
                "blocks": [
                    {
                        "text": "You: send the proposal.",
                        "citations": [{"utterance_id": you.id, "start_ms": 110_000}],
                    }
                ],
            },
        ],
    }
    json.dumps(detail)  # everything crosses the bridge as JSON


def test_a_meeting_without_note_or_transcript(conn: sqlite3.Connection) -> None:
    mid = MeetingStore(conn).create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    detail = meeting_detail(conn, mid)
    assert detail is not None
    assert (detail["utterances"], detail["note"], detail["meeting"]["has_note"]) == (
        [],
        None,
        False,
    )


def test_an_unknown_meeting_has_no_detail(conn: sqlite3.Connection) -> None:
    assert meeting_detail(conn, "nope") is None


def test_summary_duration_only_once_finished() -> None:
    base = {"id": "m", "title": "t", "started_at": 1_000, "state": "recording", "has_note": 0}
    assert meeting_summary({**base, "ended_at": None})["duration_ms"] is None
    finished = meeting_summary({**base, "ended_at": 61_000, "state": "ready"})
    assert finished == {
        "id": "m",
        "title": "t",
        "started_at": 1_000,
        "duration_ms": 60_000,
        "state": "ready",
        "has_note": False,
    }


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("  Sync   with Priya ", "Sync with Priya"),
        ("", None),
        ("   ", None),
        ("x" * 200, "x" * 200),
        ("x" * 201, None),
    ],
)
def test_titles_are_tidied_and_bounded(given: str, expected: str | None) -> None:
    assert clean_title(given) == expected
