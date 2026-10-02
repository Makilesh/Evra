import json
import sqlite3
from pathlib import Path

import pytest

from evra.config import LlmSettings
from evra.llm.provider import LlmConfigError, LlmError, LlmModelMissing, LlmTimeout, LlmUnavailable
from evra.notes.job import NothingSupported, failure_reason, write_and_save
from evra.notes.templates import load_template
from evra.notes.writer import NoteCutOff, NoteInvalid, NoteTooLong, NoTranscript
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore
from tests.unit.notes.fakes import FakeProvider

GOOD = json.dumps(
    {
        "summary": [
            {"text": "You finished the search migration on Tuesday.", "citations": ["u:1"]}
        ],
        "sections": [],
    }
)
UNSUPPORTED = json.dumps(
    {"summary": [{"text": "Everyone loved the cake.", "citations": ["u:1"]}], "sections": []}
)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _save(conn: sqlite3.Connection, reply: str) -> str:
    store = MeetingStore(conn)
    mid = store.latest_meeting_id() or store.create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.current_transcript_version(mid)
    if vid is None:
        vid = store.create_transcript_version(mid, kind="live", model="fake")
        store.add_utterance(
            version_id=vid,
            meeting_id=mid,
            channel=0,
            start_ms=0,
            end_ms=4_000,
            text="I finished the search migration on Tuesday.",
        )
    write_and_save(
        conn,
        meeting=store.get_meeting(mid),
        version_id=vid,
        utterances=store.utterances(vid),
        template=load_template("one_on_one"),
        provider=FakeProvider([reply]),
        model="fake:1b",
        settings=LlmSettings(),
    )
    return mid


def test_a_supported_note_is_saved_as_current(conn: sqlite3.Connection) -> None:
    mid = _save(conn, GOOD)
    note = NoteStore(conn).current_note(mid)
    assert note is not None and note.model == "fake:1b"


def test_a_note_with_nothing_supported_is_refused_and_the_old_one_kept(
    conn: sqlite3.Connection,
) -> None:
    mid = _save(conn, GOOD)
    before = NoteStore(conn).current_note(mid)
    with pytest.raises(NothingSupported) as caught:
        _save(conn, UNSUPPORTED)
    assert caught.value.dropped == 1
    assert NoteStore(conn).current_note(mid) == before


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (LlmUnavailable("down"), "ollama_down"),
        (LlmModelMissing("gemma4:12b"), "model_missing"),
        (LlmTimeout("slow"), "timeout"),
        (NoteTooLong(30_000, 24_000), "too_long"),
        (NoteCutOff(4096), "cut_off"),
        (NoteInvalid("m"), "invalid"),
        (NothingSupported(3), "nothing_supported"),
        (NoTranscript("none"), "no_transcript"),
        (LlmConfigError("not local"), "llm_error"),
        (LlmError("HTTP 500"), "llm_error"),
        (RuntimeError("anything"), "llm_error"),
    ],
)
def test_every_failure_has_a_fixed_reason_code(error: BaseException, reason: str) -> None:
    assert failure_reason(error) == reason
