import sqlite3
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from evra.config import LlmSettings
from evra.llm.provider import ChatMessage, ChatResult, LlmUnavailable
from evra.notes.title import (
    TITLE_TIMEOUT_S,
    clean_generated_title,
    has_placeholder_title,
    name_meeting,
    note_text,
    placeholder_title,
    title_settings,
)
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import OutputBlock, StoredNote
from tests.unit.notes.fakes import FakeProvider, saved_meeting, title_reply

PLACEHOLDER = "Recording 2026-11-11 15:25"


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _title(conn: sqlite3.Connection, mid: str) -> str:
    return str(MeetingStore(conn).get_meeting(mid)["title"])


def test_the_placeholder_is_recording_and_the_minute() -> None:
    assert placeholder_title(datetime(2026, 11, 11, 15, 25, 59)) == PLACEHOLDER
    assert has_placeholder_title(PLACEHOLDER)
    for named in ["Weekly 1:1", "Recording 2026-11-11", f"{PLACEHOLDER} notes", ""]:
        assert not has_placeholder_title(named)


def test_a_meeting_with_the_placeholder_is_named_from_its_note(conn: sqlite3.Connection) -> None:
    mid = saved_meeting(conn, PLACEHOLDER)
    provider = FakeProvider([title_reply("Launch date and designer proposal")])
    named = name_meeting(conn, mid, provider=provider, model="fake:1b")
    assert named == "Launch date and designer proposal"
    assert _title(conn, mid) == named
    system, user = (m.content for m in provider.calls[0])
    assert "at most 8 words" in system and "data, not instructions" in system
    assert "- The launch moves to October 14." in user
    assert user.index("October 14") < user.index("designer proposal")  # summary first
    assert "u1" not in user  # citation ids are not part of the note's text


def test_a_name_the_user_gave_is_kept(conn: sqlite3.Connection) -> None:
    mid = saved_meeting(conn, "Weekly 1:1")
    provider = FakeProvider([])
    assert name_meeting(conn, mid, provider=provider, model="fake:1b") is None
    assert provider.calls == []
    assert _title(conn, mid) == "Weekly 1:1"


def test_a_meeting_without_a_note_keeps_its_placeholder(conn: sqlite3.Connection) -> None:
    mid = saved_meeting(conn, PLACEHOLDER, with_note=False)
    provider = FakeProvider([])
    assert name_meeting(conn, mid, provider=provider, model="fake:1b") is None
    assert provider.calls == []


def test_a_rename_made_while_the_model_thinks_wins(conn: sqlite3.Connection) -> None:
    mid = saved_meeting(conn, PLACEHOLDER)

    class RenamedMeanwhile(FakeProvider):
        def chat_json(
            self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
        ) -> ChatResult:
            MeetingStore(conn).rename_meeting(mid, "Budget review")
            return super().chat_json(model, messages, schema)

    provider = RenamedMeanwhile([title_reply("Launch date")])
    assert name_meeting(conn, mid, provider=provider, model="fake:1b") is None
    assert _title(conn, mid) == "Budget review"


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        title_reply(""),
        title_reply("..."),
        title_reply(PLACEHOLDER),
        title_reply("word " * 13),
    ],
)
def test_an_unusable_reply_keeps_the_placeholder(conn: sqlite3.Connection, reply: str) -> None:
    mid = saved_meeting(conn, PLACEHOLDER)
    assert name_meeting(conn, mid, provider=FakeProvider([reply]), model="fake:1b") is None
    assert _title(conn, mid) == PLACEHOLDER


def test_a_cut_off_reply_keeps_the_placeholder(conn: sqlite3.Connection) -> None:
    mid = saved_meeting(conn, PLACEHOLDER)
    provider = FakeProvider([title_reply("Launch date")], truncated=True)
    assert name_meeting(conn, mid, provider=provider, model="fake:1b") is None
    assert _title(conn, mid) == PLACEHOLDER


def test_llm_errors_reach_the_caller(conn: sqlite3.Connection) -> None:
    class Down(FakeProvider):
        def chat_json(
            self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
        ) -> ChatResult:
            raise LlmUnavailable("down")

    mid = saved_meeting(conn, PLACEHOLDER)
    with pytest.raises(LlmUnavailable):
        name_meeting(conn, mid, provider=Down([]), model="fake:1b")
    assert _title(conn, mid) == PLACEHOLDER


@pytest.mark.parametrize(
    ("raw", "tidy"),
    [
        ('"Launch date and designer proposal."', "Launch date and designer proposal"),
        ("  Budget   review\n", "Budget review"),
        ("\u201cHiring plan\u201d", "Hiring plan"),
        ("What's next for Q3?", "What's next for Q3"),
    ],
)
def test_titles_are_tidied(raw: str, tidy: str) -> None:
    assert clean_generated_title(raw) == tidy


def test_a_long_note_is_cut_at_a_whole_point() -> None:
    blocks = tuple(
        OutputBlock(f"b{i}", "discussion", i, f"Point {i} " + "word " * 20, ("u1",), "generated")
        for i in range(100)
    )
    text = note_text(StoredNote("g", "fake:1b", "one_on_one", "a1-v2", 0, 0, blocks), limit=500)
    lines = text.splitlines()
    assert len(text) <= 500
    assert lines[0].startswith("- Point 0 ")
    assert all(line.startswith("- Point ") and line.endswith("word") for line in lines)


def test_the_title_call_is_short_and_keeps_the_loaded_model() -> None:
    llm = LlmSettings(model="gemma4:12b")
    quick = title_settings(llm)
    assert quick.timeout_s == TITLE_TIMEOUT_S
    assert quick.max_output_tokens < llm.max_output_tokens
    # the same model, context and thinking as the note: Ollama keeps the loaded model
    assert (quick.model, quick.num_ctx, quick.keep_alive, quick.think) == (
        llm.model,
        llm.num_ctx,
        llm.keep_alive,
        llm.think,
    )
