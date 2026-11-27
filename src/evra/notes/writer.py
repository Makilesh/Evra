"""Writes one note in a single pass (BUILD.md §7.4-7.5): A1 -> JSON -> at most one A9 repair ->
grounding (the word check, and the meaning check when one is given). Drafting and checking are
two steps, so the note job can make its other model calls in between and keep every embedding
request after the last of them (§8.3). A1 writes the note's own sections; decisions, action items
and open questions are listed by A4-A6, so a point A1 still puts there is set aside. Nothing here
logs or raises with prompt, reply or transcript text."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog

from evra.config import LlmSettings
from evra.llm.provider import ChatMessage, ChatResult, LlmProvider
from evra.llm.schemas import NoteDraft
from evra.notes.context import MeetingContext, build_context
from evra.notes.errors import (
    NoteCutOff,
    NoteError,
    NoteInvalid,
    NoteTooLong,
    NoTranscript,
)
from evra.notes.prompt_input import note_prompt
from evra.notes.semantic import SemanticCheck
from evra.notes.structured import chat_structured
from evra.notes.templates import Template
from evra.notes.validate import CheckedNote, check_note
from evra.store.meetings import Utterance

__all__ = [
    "DraftedNote",
    "NoTranscript",
    "NoteCutOff",
    "NoteError",
    "NoteInvalid",
    "NoteResult",
    "NoteTooLong",
    "check_drafted",
    "cut_to_fit",
    "draft_note",
    "lists_only",
    "note_prompt_tokens",
    "prompt_limit",
    "synthesis_only",
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
    items_only: bool = False  # A1 failed: the note is its action items, decisions and questions


@dataclass(frozen=True)
class DraftedNote:
    """A1's reply, parsed and not yet checked."""

    draft: NoteDraft
    model: str
    prompt_version: str  # "a0-v1+a1-v4", with "+a9-v1" after a repair
    tokens_in: int
    tokens_out: int
    seconds: float
    repaired: bool


def prompt_limit(settings: LlmSettings, *, reply: int | None = None) -> int:
    """What one note prompt may use: the budget, never more than the context minus the reply's
    room (`reply`, else the settings' own)."""
    return min(settings.context_budget, settings.num_ctx - (reply or settings.max_output_tokens))


def cut_to_fit(settings: LlmSettings, *, reply: int | None = None) -> Callable[[ChatResult], None]:
    """Raises NoteTooLong when Ollama cut the prompt to fit its context window: its count of
    what it read reaches the context minus the reply's room."""
    room = settings.num_ctx - (reply or settings.max_output_tokens)

    def too_long(first: ChatResult) -> None:
        if first.tokens_in >= room:
            raise NoteTooLong(first.tokens_in, room)

    return too_long


def note_prompt_tokens(context: MeetingContext, template: Template) -> int:
    """A1's estimated size: what `draft_note` checks against the budget."""
    return note_prompt(
        context, template=template, schema=NoteDraft.model_json_schema()
    ).estimated_tokens


def draft_note(
    provider: LlmProvider,
    *,
    model: str,
    context: MeetingContext,
    template: Template,
    settings: LlmSettings,
) -> DraftedNote:
    schema = NoteDraft.model_json_schema()
    prompt = note_prompt(context, template=template, schema=schema)
    limit = prompt_limit(settings)
    if prompt.estimated_tokens > limit:
        raise NoteTooLong(prompt.estimated_tokens, limit)
    messages = [ChatMessage("system", prompt.system), ChatMessage("user", prompt.user)]
    reply = chat_structured(
        provider,
        model,
        messages,
        NoteDraft,
        max_output_tokens=settings.max_output_tokens,
        invalid_event="note_json_invalid",
        after_first=cut_to_fit(settings),
    )
    version = prompt.prompt_version
    if reply.repair_version:
        version = f"{version}+{reply.repair_version}"
    return DraftedNote(
        draft=reply.value,
        model=model,
        prompt_version=version,
        tokens_in=reply.tokens_in,
        tokens_out=reply.tokens_out,
        seconds=reply.seconds,
        repaired=reply.repaired,
    )


NO_POINTS = CheckedNote((), (), 0, 0, {})


def lists_only(*, model: str, prompt_version: str, template: Template) -> NoteResult:
    """The note of its action items, decisions and open questions alone (§9.1): the call that
    writes its own sections failed even after its repair, so its reply adds nothing."""
    return NoteResult(
        note=NO_POINTS,
        model=model,
        prompt_version=prompt_version,
        template=template.id,
        tokens_in=0,
        tokens_out=0,
        seconds=0.0,
        repaired=False,
        items_only=True,
    )


def synthesis_only(draft: NoteDraft, template: Template) -> tuple[NoteDraft, int]:
    """The draft without the template's extraction sections (their records fill them), and how
    many points it had there."""
    listed = {s.id for s in template.sections if s.source == "extraction"}
    own = [s for s in draft.sections if s.section_id not in listed]
    set_aside = sum(len(s.bullets) for s in draft.sections if s.section_id in listed)
    return draft.model_copy(update={"sections": own}), set_aside


def check_drafted(
    drafted: DraftedNote,
    *,
    context: MeetingContext,
    template: Template,
    semantic: SemanticCheck | None = None,
) -> NoteResult:
    """The check (its one embedding batch, when a meaning check is given) and the result."""
    draft, set_aside = synthesis_only(drafted.draft, template)
    note = check_note(
        draft,
        aliases=context.aliases,
        utterance_text=context.utterance_text,
        template=template,
        semantic=semantic,
    )
    log.info(
        "note_written",
        model=drafted.model,
        kept=note.kept,
        dropped=note.dropped,
        rescued=note.rescued,
        reasons=dict(note.drop_reasons),
        repaired=drafted.repaired,
        set_aside=set_aside,
    )
    return NoteResult(
        note=note,
        model=drafted.model,
        prompt_version=drafted.prompt_version,
        template=template.id,
        tokens_in=drafted.tokens_in,
        tokens_out=drafted.tokens_out,
        seconds=drafted.seconds,
        repaired=drafted.repaired,
    )


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
    """The note's own sections alone (A1 and its check). The note job also lists the items
    (`evra.notes.job`)."""
    if not utterances:
        raise NoTranscript("no transcript")
    context = build_context(meeting=meeting, utterances=utterances, gaps=gaps)
    drafted = draft_note(
        provider, model=model, context=context, template=template, settings=settings
    )
    return check_drafted(drafted, context=context, template=template, semantic=semantic)
