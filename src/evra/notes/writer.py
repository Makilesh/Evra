"""Writes one note in a single pass (BUILD.md §7.4-7.5): A1 -> JSON -> at most one A9 repair ->
grounding. Nothing here logs or raises with prompt, reply or transcript text."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic import ValidationError

from evra.config import LlmSettings
from evra.llm.prompt_files import load_prompt
from evra.llm.provider import ChatMessage, ChatResult, LlmProvider
from evra.llm.schemas import NoteDraft
from evra.notes.prompt_input import build_note_prompt
from evra.notes.templates import Template
from evra.notes.validate import CheckedNote, check_note
from evra.store.meetings import Utterance

log = structlog.get_logger(__name__)


class NoteError(Exception):
    """The note could not be written."""


class NoTranscript(NoteError):
    """There is nothing to write a note from."""


class NoteTooLong(NoteError):
    def __init__(self, estimated: int, limit: int) -> None:
        super().__init__(f"about {estimated} prompt tokens, limit {limit}")
        self.estimated = estimated
        self.limit = limit


class NoteInvalid(NoteError):
    def __init__(self, model: str) -> None:
        super().__init__(f"{model} returned invalid JSON twice")
        self.model = model


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


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        stripped = stripped.rstrip().removesuffix("```")
    return stripped.strip()


def _parse(content: str) -> tuple[NoteDraft | None, str]:
    try:
        return NoteDraft.model_validate_json(_strip_fences(content)), ""
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(p) for p in e['loc']) or 'document'}: {e['msg']}"
            for e in exc.errors(include_input=False, include_url=False)
        ]
        return None, "; ".join(problems)[:2000]


def write_note(
    provider: LlmProvider,
    *,
    model: str,
    meeting: Mapping[str, Any],
    utterances: Sequence[Utterance],
    template: Template,
    settings: LlmSettings,
    gaps: Sequence[Mapping[str, Any]] = (),
) -> NoteResult:
    if not utterances:
        raise NoTranscript("no transcript")
    schema = NoteDraft.model_json_schema()
    prompt = build_note_prompt(
        meeting=meeting, utterances=utterances, template=template, schema=schema, gaps=gaps
    )
    if prompt.estimated_tokens > settings.context_budget:
        raise NoteTooLong(prompt.estimated_tokens, settings.context_budget)
    messages = [ChatMessage("system", prompt.system), ChatMessage("user", prompt.user)]
    calls: list[ChatResult] = [provider.chat_json(model, messages, schema)]
    room = settings.num_ctx - settings.max_output_tokens
    if calls[0].tokens_in >= room:  # Ollama cut the prompt to fit its context window
        raise NoteTooLong(calls[0].tokens_in, room)
    draft, error = _parse(calls[0].content)
    version = prompt.prompt_version
    if draft is None:
        repair = load_prompt("a9_repair")
        system, user = repair.render(
            schema=json.dumps(schema, separators=(",", ":")),
            error=error,
            bad_output=calls[0].content,
        )
        repair_messages = [ChatMessage("system", system), ChatMessage("user", user)]
        calls.append(provider.chat_json(model, repair_messages, schema))
        version = f"{version}+{repair.version}"
        draft, error = _parse(calls[1].content)
        if draft is None:
            log.warning("note_json_invalid", model=model, error=error)
            raise NoteInvalid(model)
    note = check_note(
        draft,
        aliases=prompt.aliases,
        utterance_text={u.id: u.text for u in utterances},
        template=template,
    )
    repaired = len(calls) > 1
    log.info(
        "note_written",
        model=model,
        kept=note.kept,
        dropped=note.dropped,
        reasons=dict(note.drop_reasons),
        repaired=repaired,
    )
    return NoteResult(
        note=note,
        model=model,
        prompt_version=version,
        template=template.id,
        tokens_in=sum(c.tokens_in for c in calls),
        tokens_out=sum(c.tokens_out for c in calls),
        seconds=sum(c.seconds for c in calls),
        repaired=repaired,
    )
