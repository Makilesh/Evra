"""A1's inputs (BUILD.md §7.4). Utterances appear as short prompt ids u:1…u:N in time order,
mapped back to real ids afterwards: the model copies a few characters instead of 32-character
hex ids. All data is made inert inside its tags."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from evra.llm.prompt_files import load_prompt
from evra.notes.context import (
    CHARS_PER_TOKEN,
    EN_DASH,
    NONE,
    _gap_lines,
    _one_line,
    as_data,
    transcript_lines,
)
from evra.notes.templates import Template
from evra.store.meetings import Utterance
from evra.transcribe.labels import PARTICIPANTS_1ON1

__all__ = ["CHARS_PER_TOKEN", "EN_DASH", "NONE", "as_data", "transcript_lines"]


@dataclass(frozen=True)
class NotePrompt:
    system: str
    user: str
    prompt_version: str
    aliases: Mapping[str, str]  # "u:3" -> utterance id
    estimated_tokens: int


def build_note_prompt(
    *,
    meeting: Mapping[str, Any],
    utterances: Sequence[Utterance],
    template: Template,
    schema: Mapping[str, Any],
    gaps: Sequence[Mapping[str, Any]] = (),
    language: str = "English",
) -> NotePrompt:
    if not utterances:
        raise ValueError("no utterances")
    prompt = load_prompt("a1_note")
    transcript, aliases = transcript_lines(utterances)
    end_ms = max(u.end_ms for u in utterances)
    started = datetime.fromtimestamp(int(meeting["started_at"]) / 1000)
    system, user = prompt.render(
        output_language=language,
        schema=json.dumps(schema, separators=(",", ":")),
        title=_one_line(str(meeting["title"])),
        date_iso=started.date().isoformat(),
        duration_minutes=str(max(1, round(end_ms / 60_000))),
        setting=_one_line(str(meeting.get("situation") or "unknown").replace("_", " ")),
        participants=PARTICIPANTS_1ON1,
        template_name=template.name,
        template_sections_yaml=template.sections_yaml(),
        user_notes=NONE,  # the notepad arrives in M5
        transcript=transcript,
        gaps=_gap_lines(gaps),
    )
    estimated = math.ceil((len(system) + len(user)) / CHARS_PER_TOKEN)
    return NotePrompt(system, user, prompt.version, aliases, estimated)
