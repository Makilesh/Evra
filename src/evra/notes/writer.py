"""Writes one note in a single pass (BUILD.md §7.4-7.5): A1 -> JSON -> at most one A9 repair ->
grounding (the word check, and the meaning check when one is given: its one embedding batch
runs after the model's reply). Nothing here logs or raises with prompt, reply or transcript
text."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog

from evra.config import LlmSettings
from evra.llm.provider import ChatMessage, ChatResult, LlmProvider
from evra.llm.schemas import NoteDraft
from evra.notes.errors import (
    NoteCutOff,
    NoteError,
    NoteInvalid,
    NoteTooLong,
    NoTranscript,
)
from evra.notes.prompt_input import build_note_prompt
from evra.notes.semantic import SemanticCheck
from evra.notes.structured import chat_structured
from evra.notes.templates import Template
from evra.notes.validate import CheckedNote, check_note
from evra.store.meetings import Utterance

__all__ = [
    "NoTranscript",
    "NoteCutOff",
    "NoteError",
    "NoteInvalid",
    "NoteResult",
    "NoteTooLong",
    "write_note",
]

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class NoteResult:
    note: CheckedNote
    model: str
    prompt_version: str
    template: str
    tokens_in: int
    tokens_out: int
    seconds: float
    repaired: bool


def write_note(
    provider: LlmProvider,
    *,
    model: str,
    meeting: Mapping[str, Any],
    utterances: Sequence[Utterance],
    template: Template,
    settings: LlmSettings,
    gaps: Sequence[Mapping[str, Any]] = (),
    semantic: SemanticCheck | None = None,
) -> NoteResult:
    if not utterances:
        raise NoTranscript("no transcript")
    schema = NoteDraft.model_json_schema()
    prompt = build_note_prompt(
        meeting=meeting, utterances=utterances, template=template, schema=schema, gaps=gaps
    )
    room = settings.num_ctx - settings.max_output_tokens  # what the prompt may use
    limit = min(settings.context_budget, room)
    if prompt.estimated_tokens > limit:
        raise NoteTooLong(prompt.estimated_tokens, limit)
    messages = [ChatMessage("system", prompt.system), ChatMessage("user", prompt.user)]

    def too_long(first: ChatResult) -> None:
        if first.tokens_in >= room:  # Ollama cut the prompt to fit its context window
            raise NoteTooLong(first.tokens_in, room)

    reply = chat_structured(
        provider,
        model,
        messages,
        NoteDraft,
        max_output_tokens=settings.max_output_tokens,
        invalid_event="note_json_invalid",
        after_first=too_long,
    )
    version = prompt.prompt_version
    if reply.repair_version:
        version = f"{version}+{reply.repair_version}"
    note = check_note(
        reply.value,
        aliases=prompt.aliases,
        utterance_text={u.id: u.text for u in utterances},
        template=template,
        semantic=semantic,
    )
    log.info(
        "note_written",
        model=model,
        kept=note.kept,
        dropped=note.dropped,
        rescued=note.rescued,
        reasons=dict(note.drop_reasons),
        repaired=reply.repaired,
    )
    return NoteResult(
        note=note,
        model=model,
        prompt_version=version,
        template=template.id,
        tokens_in=reply.tokens_in,
        tokens_out=reply.tokens_out,
        seconds=reply.seconds,
        repaired=reply.repaired,
    )
