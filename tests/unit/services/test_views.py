import json
import sqlite3
from pathlib import Path

import pytest

from evra.notes.extract import CheckedItem
from evra.notes.validate import CheckedBullet, CheckedNote, CheckedSection
from evra.services.views import clean_title, item_text, meeting_detail, meeting_summary
from evra.store.db import connect
from evra.store.items import ItemStore
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


def test_note_view_items_carry_status(conn: sqlite3.Connection) -> None:
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="Weekly 1:1", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    quote = store.add_utterance(
        version_id=vid,
        meeting_id=mid,
        channel=0,
        start_ms=12_000,
        end_ms=15_000,
        text="I'll send the vendor quote by Friday.",
    )
    plan = store.add_utterance(
        version_id=vid,
        meeting_id=mid,
        channel=1,
        start_ms=20_000,
        end_ms=24_000,
        text="So we go with the annual plan.",
    )
    note = CheckedNote(
        summary=(CheckedBullet("The quote goes out this week.", (quote.id,)),),
        sections=(
            CheckedSection(
                "next_time", "For next time", (CheckedBullet("Mentoring.", (plan.id,)),)
            ),
        ),
        kept=2,
        dropped=0,
        drop_reasons={},
    )
    generation = NoteStore(conn).save_generation(
        meeting_id=mid,
        transcript_version_id=vid,
        note=note,
        provider="ollama",
        model="gemma4:12b",
        prompt_version="a0-v1+a1-v4+a4-v1+a5-v1+a6-v1",
        template="one_on_one",
        tokens_in=1,
        tokens_out=1,
        items=[
            CheckedItem(
                "action_item", "Send the vendor quote", (quote.id,), "You", "by Friday", 0.9
            ),
            CheckedItem("action_item", "Book the venue", (plan.id, "user"), None, None, 0.8),
            CheckedItem("action_item", "Plan the offsite", (plan.id,), "Them", None, 0.7),
            CheckedItem("decision", "Go with the annual plan.", (plan.id,), "Them", None, None),
        ],
    )
    items = ItemStore(conn)
    send, venue, offsite, decision = items.for_generation(generation)
    assert items.set_status(send.id, "done") and items.set_status(offsite.id, "dismissed")
    detail = meeting_detail(conn, mid)
    assert detail is not None and detail["note"] is not None
    sections = detail["note"]["sections"]
    # template order, summary first; a section with nothing in it is left out
    assert [s["id"] for s in sections] == ["summary", "decisions", "action_items", "next_time"]
    assert sections[2]["title"] == "Action items"
    assert sections[2]["blocks"] == [  # the dismissed one is left out
        {
            "text": "You: Send the vendor quote (by Friday)",
            "citations": [{"utterance_id": quote.id, "start_ms": 12_000}],
            "item": {
                "id": send.id,
                "kind": "action_item",
                "status": "done",
                "owner": "You",
                "due": "by Friday",
            },
        },
        {
            "text": "Book the venue",
            "citations": [{"utterance_id": plan.id, "start_ms": 20_000}],
            "item": {
                "id": venue.id,
                "kind": "action_item",
                "status": "open",
                "owner": None,
                "due": None,
            },
        },
    ]
    assert sections[1]["blocks"] == [  # who made a decision stays in the record (RB21)
        {
            "text": "Go with the annual plan.",
            "citations": [{"utterance_id": plan.id, "start_ms": 20_000}],
            "item": {
                "id": decision.id,
                "kind": "decision",
                "status": "open",
                "owner": "Them",
                "due": None,
            },
        }
    ]
    assert "item" not in sections[0]["blocks"][0]  # the note's own points are not records
    json.dumps(detail)


def test_item_text_names_a_tasks_owner_and_its_due_date_once() -> None:
    assert item_text("action_item", "You", "Send the vendor quote", "by Friday") == (
        "You: Send the vendor quote (by Friday)"
    )
    assert item_text("action_item", None, "Book the venue", None) == "Book the venue"
    # a due date the text already says is not said again, whatever its case
    assert item_text("action_item", "You", "Write the postmortem by Friday.", "by Friday") == (
        "You: Write the postmortem by Friday."
    )
    assert item_text("action_item", "Them", "Send it BY FRIDAY", "by Friday") == (
        "Them: Send it BY FRIDAY"
    )
    # only a task shows its owner first; a decision or a question stands alone
    assert item_text("decision", "You", "You will send the proposal.", None) == (
        "You will send the proposal."
    )
    assert item_text("open_question", "Them", "Do we need batching?", None) == (
        "Do we need batching?"
    )


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


def test_meeting_detail_lists_questions(conn: sqlite3.Connection) -> None:
    from evra.notes.ask import AskResult
    from evra.store.questions import QuestionStore

    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    line = store.add_utterance(
        version_id=vid, meeting_id=mid, channel=1, start_ms=9_000, end_ms=12_000, text="Friday."
    )
    questions = QuestionStore(conn)
    first = questions.add(mid, "When?")
    questions.answer(
        first.id,
        AskResult(
            "answered",
            (CheckedBullet("Friday.", (line.id, "gone")),),
            False,
            "gemma4:12b",
            "a0-v1+a12-v1",
            10,
            5,
            1.0,
            0,
        ),
        transcript_version_id=vid,
    )
    second = questions.fail(questions.add(mid, "Who?").id, "ollama_down")
    detail = meeting_detail(conn, mid)
    assert detail is not None
    answered, failed = detail["questions"]
    assert answered["text"] == "When?" and answered["state"] == "answered"
    assert answered["points"] == [
        {"text": "Friday.", "citations": [{"utterance_id": line.id, "start_ms": 9_000}]}
    ]
    assert answered["model"] == "gemma4:12b" and answered["excerpt"] is False
    assert "reason" not in answered
    assert (failed["id"], failed["state"], failed["reason"]) == (second.id, "failed", "ollama_down")
    json.dumps(detail)


def test_a_not_discussed_view_has_no_model(conn: sqlite3.Connection) -> None:
    from evra.notes.ask import AskResult
    from evra.services.views import question_view
    from evra.store.questions import QuestionStore

    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    questions = QuestionStore(conn)
    stored = questions.answer(
        questions.add(mid, "Who?").id,
        AskResult("not_found", (), False, "gemma4:12b", "a0-v1+a12-v1", 10, 5, 1.0, 0),
        transcript_version_id=vid,
    )
    view = question_view(stored, {})
    assert view["state"] == "not_found"
    assert "model" not in view and "reason" not in view
