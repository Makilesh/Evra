"""Write a stored meeting's note and keep it (BUILD.md §7.3-7.5, §8.3), shared by `evra note` and
the window (M3c). Every call reads one meeting context: A1 writes the note's own sections, then
A4-A6 list its action items, decisions and open questions; the checks' embedding batches come
after every chat call, so Ollama never swaps models mid-way; the note and its items are saved in
one transaction. A call longer than `llm.single_pass_minutes`, or too long for one prompt, is
read in parts and combined instead (A2/A3, `evra.notes.mapreduce`). When A1's JSON fails even
after its repair, the items make the note on their own (§9.1). An empty note is never saved, so
it can never hide an earlier one."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog

from evra.config import LlmSettings
from evra.llm.provider import (
    LlmModelMissing,
    LlmNotLocal,
    LlmProvider,
    LlmTimeout,
    LlmUnavailable,
)
from evra.notes.context import NONE, build_context
from evra.notes.extract import ALL_KINDS, ITEM_SECTIONS, Extraction, ItemKind, extract_items
from evra.notes.mapreduce import write_long_note
from evra.notes.semantic import SemanticCheck
from evra.notes.templates import Template
from evra.notes.validate import Grounder
from evra.notes.windows import choose_path
from evra.notes.writer import (
    DraftedNote,
    NoteCutOff,
    NoteError,
    NoteInvalid,
    NoteResult,
    NoteTooLong,
    NoTranscript,
    check_drafted,
    draft_note,
    lists_only,
    note_prompt_tokens,
)
from evra.store.meetings import Utterance
from evra.store.notes import NoteStore

log = structlog.get_logger(__name__)


class NothingSupported(NoteError):
    def __init__(self, dropped: int) -> None:
        super().__init__(f"{dropped} points dropped as unsupported")
        self.dropped = dropped


@dataclass(frozen=True)
class SavedNote:
    result: NoteResult  # the note's own sections
    extraction: Extraction  # its action items, decisions and open questions
    generation_id: str


_REASONS: tuple[tuple[type[BaseException], str], ...] = (
    (LlmUnavailable, "ollama_down"),
    (LlmModelMissing, "model_missing"),
    (LlmNotLocal, "cloud_model"),
    (LlmTimeout, "timeout"),
    (NoteTooLong, "too_long"),
    (NoteCutOff, "cut_off"),
    (NoteInvalid, "invalid"),
    (NothingSupported, "nothing_supported"),
    (NoTranscript, "no_transcript"),
)


def failure_reason(exc: BaseException) -> str:
    """A fixed code the window turns into a sentence (M3c spec §4.1); never the error's text."""
    for kind, reason in _REASONS:
        if isinstance(exc, kind):
            return reason
    return "llm_error"


def _quiet(stage: str) -> None:
    """No one is shown the stages."""


def item_kinds(template: Template) -> tuple[ItemKind, ...]:
    """The kinds of record the template shows, in the order they are asked for (A4, A5, A6)."""
    listed = {s.id for s in template.sections if s.source == "extraction"}
    return tuple(kind for kind in ALL_KINDS if ITEM_SECTIONS[kind] in listed)


def generation_version(result: NoteResult, extraction: Extraction) -> str:
    """The A0 version, the note's own part (with "+a9-v1" after a repair) and each list's:
    a0-v1+a1-v4+a4-v2+a5-v2+a6-v2. A note of the lists alone has no A1 part."""
    return "+".join([result.prompt_version, *extraction.prompt_versions])


def write_note_and_items(
    provider: LlmProvider,
    *,
    model: str,
    meeting: Mapping[str, Any],
    utterances: Sequence[Utterance],
    template: Template,
    settings: LlmSettings,
    semantic: SemanticCheck | None = None,
    on_stage: Callable[[str], None] = _quiet,
) -> tuple[NoteResult, Extraction]:
    """The note's own sections and its records, checked, not yet saved. A call too long for
    one pass is read in parts (stages "part:i:n", then "combining"); otherwise A1 writes the
    note ("writing"), then A4-A6 list the records ("items"). A1's NoteTooLong and NoteCutOff
    stop here; its NoteInvalid only when nothing was listed either."""
    if not utterances:
        raise NoTranscript("no transcript")
    context = build_context(meeting=meeting, utterances=utterances)
    grounder = Grounder(
        aliases=context.aliases, utterance_text=context.utterance_text, semantic=semantic
    )
    # on the estimate draft_note checks, so a call too long for one prompt is read in parts
    tokens = note_prompt_tokens(context, template)
    if choose_path(utterances=utterances, prompt_tokens=tokens, settings=settings) == "windows":
        return write_long_note(
            provider,
            model=model,
            meeting=meeting,
            utterances=utterances,
            template=template,
            settings=settings,
            grounder=grounder,
            user_notes=NONE,
            on_stage=on_stage,
        )
    on_stage("writing")
    drafted: DraftedNote | None = None
    invalid: NoteInvalid | None = None
    try:
        drafted = draft_note(
            provider, model=model, context=context, template=template, settings=settings
        )
    except NoteInvalid as exc:  # the lists can still make a note (§9.1)
        invalid = exc
    kinds = item_kinds(template)
    if kinds:
        on_stage("items")
    extraction = extract_items(
        provider, model=model, context=context, settings=settings, grounder=grounder, kinds=kinds
    )
    if extraction.failed_kinds:  # their sections stay empty
        log.info("note_items_failed", kinds=list(extraction.failed_kinds))
    if drafted is None:
        assert invalid is not None
        if not extraction.items:
            raise invalid
        log.info("note_from_items", items=len(extraction.items))
        # no A1 part in its version: its reply was not used
        return lists_only(model=model, prompt_version=context.version, template=template), (
            extraction
        )
    # the note's own check comes last: its embedding batch follows every chat call
    result = check_drafted(drafted, context=context, template=template, semantic=semantic)
    return result, extraction


def write_and_save(
    conn: sqlite3.Connection,
    *,
    meeting: Mapping[str, Any],
    version_id: str,
    utterances: Sequence[Utterance],
    template: Template,
    provider: LlmProvider,
    model: str,
    settings: LlmSettings,
    semantic: SemanticCheck | None = None,
    on_stage: Callable[[str], None] = _quiet,
) -> SavedNote:
    result, extraction = write_note_and_items(
        provider,
        model=model,
        meeting=meeting,
        utterances=utterances,
        template=template,
        settings=settings,
        semantic=semantic,
        on_stage=on_stage,
    )
    if result.note.kept == 0 and not extraction.items:  # never replace a usable note with nothing
        raise NothingSupported(result.note.dropped + extraction.dropped)
    generation_id = NoteStore(conn).save_generation(
        meeting_id=str(meeting["id"]),
        transcript_version_id=version_id,
        note=result.note,
        provider=provider.name,
        model=result.model,
        prompt_version=generation_version(result, extraction),
        template=template.id,
        tokens_in=result.tokens_in + extraction.tokens_in,
        tokens_out=result.tokens_out + extraction.tokens_out,
        items=extraction.items,
        items_dropped=extraction.dropped,
    )
    return SavedNote(result, extraction, generation_id)
