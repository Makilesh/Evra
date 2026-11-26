"""A1's inputs (BUILD.md §7.4). Utterances appear as short prompt ids u:1…u:N in time order,
mapped back to real ids afterwards: the model copies a few characters instead of 32-character
hex ids. All data is made inert inside its tags."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evra.llm.prompt_files import load_part
from evra.notes.context import (
    CHARS_PER_TOKEN,
    EN_DASH,
    NONE,
    as_data,
    build_context,
    estimate_tokens,
    transcript_lines,
)
from evra.notes.templates import Template
from evra.store.meetings import Utterance

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
    context = build_context(meeting=meeting, utterances=utterances, gaps=gaps, user_notes=NONE)
    task = load_part("a1_note")
    user = task.render(
        output_language=language,
        schema=json.dumps(schema, separators=(",", ":")),
        template_name=template.name,
        template_sections_yaml=template.sections_yaml(),
    )
    return NotePrompt(
        system=context.system,
        user=user,
        prompt_version=f"{context.version}+{task.version}",
        aliases=context.aliases,
        estimated_tokens=estimate_tokens(context.system + user),
    )
