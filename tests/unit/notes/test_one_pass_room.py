"""A call near the budget stays in one pass (RB64). The budget is 28,400; when Ollama cuts A1's
prompt anyway (its count reaches the room although the estimate fit), the call is read in parts
instead of failing. A4-A6 share A1's context with smaller tasks, so once A1's prompt fits every
one-pass prompt fits, and a note A1 has written is never lost to a cut list prompt."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import structlog

from evra.config import LlmSettings
from evra.llm.prompt_files import load_part
from evra.llm.provider import ChatMessage, ChatResult
from evra.llm.schemas import ActionItems, Decisions, NoteDraft, OpenQuestions
from evra.notes.context import build_context, estimate_tokens
from evra.notes.prompt_input import note_prompt
from evra.notes.templates import load_template
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from tests.unit.notes.fakes import FakeProvider
from tests.unit.notes.test_job import GOOD, _long_meeting, _write_long
from tests.unit.notes.test_mapreduce import PART1, PART2, combined


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


class CutsTheFirstPrompt(FakeProvider):
    """Ollama read the first prompt (A1's) up to the room it has after the reply, so it was cut;
    every later prompt fits."""

    def chat_json(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        schema: Mapping[str, Any],
        *,
        max_output_tokens: int | None = None,
    ) -> ChatResult:
        result = super().chat_json(model, messages, schema, max_output_tokens=max_output_tokens)
        if len(self.calls) == 1:
            settings = LlmSettings()
            return replace(result, tokens_in=settings.num_ctx - settings.max_output_tokens)
        return result


def test_the_default_budget_is_just_under_the_room() -> None:
    settings = LlmSettings()
    assert settings.context_budget == 28_400
    assert settings.context_budget < settings.num_ctx - settings.max_output_tokens  # 28,672


def test_a_cut_one_pass_prompt_is_read_in_parts(conn: sqlite3.Connection) -> None:
    mid = _long_meeting(conn)  # 15 minutes: one pass by its length and its estimate
    provider = CutsTheFirstPrompt([GOOD, PART1, PART2, combined()])
    stages: list[str] = []
    with structlog.testing.capture_logs() as logs:
        saved = _write_long(conn, mid, provider, LlmSettings(), stages)
    assert stages == ["writing", "part:1:2", "part:2:2", "combining"]
    assert provider.calls[0][1].content.startswith("Write the note for the meeting above.")
    assert provider.calls[1][1].content.startswith("Summarise this part of the meeting")
    assert saved.result.prompt_version == "a0-v1+a2-v1+a3-v2"
    cut = [e for e in logs if e["event"] == "note_prompt_cut"]
    assert cut == [
        {"event": "note_prompt_cut", "tokens": 28_672, "room": 28_672, "log_level": "info"}
    ]


def _list_tasks() -> dict[str, str]:
    """A4-A6's user messages, rendered as extract_items renders them."""
    tasks = {}
    for prompt_id, model in (
        ("a4_actions", ActionItems),
        ("a5_decisions", Decisions),
        ("a6_questions", OpenQuestions),
    ):
        schema = json.dumps(model.model_json_schema(), separators=(",", ":"))
        tasks[prompt_id] = load_part(prompt_id).render(schema=schema)
    return tasks


@pytest.mark.parametrize("template_id", ["one_on_one", "general"])
def test_a1_is_the_largest_one_pass_prompt(conn: sqlite3.Connection, template_id: str) -> None:
    """The path is chosen on A1's estimate; A4-A6 send the same context with a smaller task."""
    mid = _long_meeting(conn)
    store = MeetingStore(conn)
    vid = store.current_transcript_version(mid)
    assert vid is not None
    context = build_context(meeting=store.get_meeting(mid), utterances=store.utterances(vid))
    a1 = note_prompt(
        context, template=load_template(template_id), schema=NoteDraft.model_json_schema()
    )
    for prompt_id, task in _list_tasks().items():
        assert estimate_tokens(context.system + task) < a1.estimated_tokens, prompt_id
