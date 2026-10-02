"""Write a stored meeting's note and keep it (M3b rules), shared by `evra note` and the
window (M3c). An empty note is never saved, so it can never hide an earlier one."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evra.config import LlmSettings
from evra.llm.provider import LlmModelMissing, LlmProvider, LlmTimeout, LlmUnavailable
from evra.notes.templates import Template
from evra.notes.writer import (
    NoteCutOff,
    NoteError,
    NoteInvalid,
    NoteResult,
    NoteTooLong,
    NoTranscript,
    write_note,
)
from evra.store.meetings import Utterance
from evra.store.notes import NoteStore


class NothingSupported(NoteError):
    def __init__(self, dropped: int) -> None:
        super().__init__(f"{dropped} points dropped as unsupported")
        self.dropped = dropped


@dataclass(frozen=True)
class SavedNote:
    result: NoteResult
    generation_id: str


_REASONS: tuple[tuple[type[BaseException], str], ...] = (
    (LlmUnavailable, "ollama_down"),
    (LlmModelMissing, "model_missing"),
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
) -> SavedNote:
    result = write_note(
        provider,
        model=model,
        meeting=meeting,
        utterances=utterances,
        template=template,
        settings=settings,
    )
    if result.note.kept == 0:  # never replace a usable note with an empty one
        raise NothingSupported(result.note.dropped)
    generation_id = NoteStore(conn).save_generation(
        meeting_id=str(meeting["id"]),
        transcript_version_id=version_id,
        note=result.note,
        provider=provider.name,
        model=result.model,
        prompt_version=result.prompt_version,
        template=template.id,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
    )
    return SavedNote(result, generation_id)
