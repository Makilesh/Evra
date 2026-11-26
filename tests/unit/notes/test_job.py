import json
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import structlog

from evra.config import LlmSettings
from evra.llm.provider import (
    ChatMessage,
    ChatResult,
    LlmConfigError,
    LlmError,
    LlmModelMissing,
    LlmNotLocal,
    LlmTimeout,
    LlmUnavailable,
)
from evra.notes.job import NothingSupported, SavedNote, failure_reason, write_and_save
from evra.notes.semantic import Embedder, SemanticCheck
from evra.notes.templates import load_template
from evra.notes.writer import NoteCutOff, NoteInvalid, NoteTooLong, NoTranscript
from evra.store.db import connect
from evra.store.items import ItemStore
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
WITH_A_PARAPHRASE = json.dumps(  # its second point shares no words with its line: a meaning check
    {
        "summary": [
            {"text": "You finished the search migration on Tuesday.", "citations": ["u:1"]},
            {"text": "Everyone loved the cake.", "citations": ["u:1"]},
        ],
        "sections": [],
    }
)
NO_ITEMS = json.dumps({"items": []})
LINES = [
    (0, 0, "I finished the search migration on Tuesday."),
    (0, 5_000, "I'll send the designer proposal by Thursday."),
    (1, 9_000, "So we go with the annual plan, agreed."),
]
PROPOSAL = {
    "text": "Send the designer proposal",
    "owner": "me",
    "due": "by Thursday",
    "confidence": 0.9,
    "citations": ["u:2"],
}
ACTIONS = json.dumps({"items": [PROPOSAL]})
DECISIONS = json.dumps(
    {"items": [{"statement": "Go with the annual plan.", "made_by": None, "citations": ["u:3"]}]}
)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


class Ordered(FakeProvider):
    """Notes whether each request was a chat or an embedding, in order."""

    def __init__(self, replies: list[str]) -> None:
        super().__init__(replies)
        self.order: list[str] = []

    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        self.order.append("chat")
        return super().chat_json(model, messages, schema)

    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        self.order.append("embed")
        return super().embed(model, texts)


class NoEmbeddings(FakeProvider):
    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        raise LlmModelMissing(model)


def _meeting(conn: sqlite3.Connection) -> str:
    store = MeetingStore(conn)
    mid = store.latest_meeting_id()
    if mid is not None:
        return mid
    mid = store.create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    for channel, start_ms, text in LINES:
        store.add_utterance(
            version_id=vid,
            meeting_id=mid,
            channel=channel,
            start_ms=start_ms,
            end_ms=start_ms + 4_000,
            text=text,
        )
    return mid


def _write(
    conn: sqlite3.Connection,
    provider: FakeProvider,
    *,
    semantic: SemanticCheck | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> SavedNote:
    store = MeetingStore(conn)
    mid = _meeting(conn)
    vid = store.current_transcript_version(mid)
    assert vid is not None
    extra: dict[str, Any] = {} if on_stage is None else {"on_stage": on_stage}
    return write_and_save(
        conn,
        meeting=store.get_meeting(mid),
        version_id=vid,
        utterances=store.utterances(vid),
        template=load_template("one_on_one"),
        provider=provider,
        model="fake:1b",
        settings=LlmSettings(),
        semantic=semantic,
        **extra,
    )


def _save(conn: sqlite3.Connection, reply: str) -> str:
    """A note from `reply` (A1), with no items (A4-A6 find nothing)."""
    _write(conn, FakeProvider([reply, NO_ITEMS, NO_ITEMS, NO_ITEMS]))
    return _meeting(conn)


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


def test_pipeline_runs_note_then_items(conn: sqlite3.Connection) -> None:
    cake = PROPOSAL | {"text": "Bake a cake for the team", "due": None}  # for the meaning check
    actions = json.dumps({"items": [PROPOSAL, cake]})
    provider = Ordered([WITH_A_PARAPHRASE, actions, DECISIONS, NO_ITEMS])
    stages: list[str] = []
    saved = _write(
        conn,
        provider,
        semantic=SemanticCheck(Embedder(provider, "embed")),
        on_stage=stages.append,
    )
    assert stages == ["writing", "items"]
    tasks = ("Write the note", "List the action items", "List the decisions", "List the questions")
    assert len(provider.calls) == len(tasks)
    for call, task in zip(provider.calls, tasks, strict=True):  # A1, A4, A5, A6
        assert call[1].content.startswith(task)
    assert len({call[0].content for call in provider.calls}) == 1  # one context for every call
    # §8.3: every chat call first, then the checks' embedding batches
    assert provider.order[:4] == ["chat"] * 4
    assert provider.order[4:] and set(provider.order[4:]) == {"embed"}
    stored = NoteStore(conn).current_note(_meeting(conn))
    assert stored is not None and stored.generation_id == saved.generation_id
    assert stored.prompt_version == "a0-v1+a1-v4+a4-v1+a5-v1+a6-v1"
    assert [b.text for b in stored.blocks] == ["You finished the search migration on Tuesday."]
    items = ItemStore(conn).for_generation(saved.generation_id)
    assert [(i.kind, i.text, i.owner, i.due) for i in items] == [
        ("action_item", "Send the designer proposal", "You", "by Thursday"),
        ("decision", "Go with the annual plan.", None, None),
    ]
    row = conn.execute(
        "SELECT tokens_in, tokens_out FROM generation WHERE id = ?", (saved.generation_id,)
    ).fetchone()
    assert (row["tokens_in"], row["tokens_out"]) == (400, 200)  # the note and its three lists


def test_fallback_note_from_items(conn: sqlite3.Connection) -> None:
    saved = _write(conn, FakeProvider(["{", "{", ACTIONS, NO_ITEMS, NO_ITEMS]))
    stored = NoteStore(conn).current_note(_meeting(conn))
    assert stored is not None and stored.generation_id == saved.generation_id
    assert stored.prompt_version == "a0-v1+a4-v1+a5-v1+a6-v1"  # no A1 part: its JSON failed
    assert stored.blocks == ()
    items = ItemStore(conn).for_generation(saved.generation_id)
    assert [i.text for i in items] == ["Send the designer proposal"]
    with pytest.raises(NoteInvalid):  # nothing listed either: the note fails, the old one stays
        _write(conn, FakeProvider(["{", "{", NO_ITEMS, NO_ITEMS, NO_ITEMS]))
    again = NoteStore(conn).current_note(_meeting(conn))
    assert again is not None and again.generation_id == saved.generation_id


def test_a_note_is_kept_for_its_items_alone(conn: sqlite3.Connection) -> None:
    saved = _write(conn, FakeProvider([UNSUPPORTED, ACTIONS, NO_ITEMS, NO_ITEMS]))
    assert (saved.result.note.kept, saved.result.note.dropped) == (0, 1)
    stored = NoteStore(conn).current_note(_meeting(conn))
    assert stored is not None and stored.blocks == ()
    assert len(ItemStore(conn).for_generation(saved.generation_id)) == 1


def test_note_written_without_embeddings(conn: sqlite3.Connection) -> None:
    provider = NoEmbeddings([WITH_A_PARAPHRASE, ACTIONS, NO_ITEMS, NO_ITEMS])
    with structlog.testing.capture_logs() as logs:
        saved = _write(conn, provider, semantic=SemanticCheck(Embedder(provider, "embed")))
    assert NoteStore(conn).current_note(_meeting(conn)) is not None
    note = saved.result.note
    assert (note.kept, note.dropped, note.rescued) == (1, 1, 0)  # the word check's verdicts
    assert len(saved.extraction.items) == 1
    skipped = [e for e in logs if e["event"] == "semantic_check_skipped"]
    assert skipped and all(e["error"] == "LlmModelMissing" for e in skipped)


def test_a_failed_list_leaves_its_section_empty(conn: sqlite3.Connection) -> None:
    provider = FakeProvider([GOOD, ACTIONS, "nope", "still nope", NO_ITEMS])
    with structlog.testing.capture_logs() as logs:
        saved = _write(conn, provider)
    assert [i.kind for i in ItemStore(conn).for_generation(saved.generation_id)] == ["action_item"]
    failed = [e for e in logs if e["event"] == "note_items_failed"]
    assert failed == [{"event": "note_items_failed", "kinds": ["decision"], "log_level": "info"}]
    stored = NoteStore(conn).current_note(_meeting(conn))
    assert stored is not None and stored.prompt_version == "a0-v1+a1-v4+a4-v1+a6-v1"


def test_a_cut_off_note_stops_before_the_lists(conn: sqlite3.Connection) -> None:
    provider = FakeProvider([GOOD[:40]], truncated=True)
    with pytest.raises(NoteCutOff):
        _write(conn, provider)
    assert len(provider.calls) == 1


def test_nothing_is_logged_with_content(conn: sqlite3.Connection) -> None:
    with structlog.testing.capture_logs() as logs:
        _write(conn, FakeProvider([GOOD, ACTIONS, DECISIONS, NO_ITEMS]))
    text = json.dumps(logs, default=str)
    assert "migration" not in text and "designer" not in text and "annual" not in text


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (LlmUnavailable("down"), "ollama_down"),
        (LlmModelMissing("gemma4:12b"), "model_missing"),
        (LlmNotLocal("m"), "cloud_model"),
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
