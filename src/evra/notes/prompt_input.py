"""A1's inputs (BUILD.md §7.4). Utterances appear as short prompt ids u:1…u:N in time order,
mapped back to real ids afterwards: the model copies a few characters instead of 32-character
hex ids. All data is made inert inside its tags. A1 is shown only the template sections it writes;
decisions, action items and open questions are listed by A4-A6 (v4)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from evra.llm.prompt_files import load_part
from evra.notes.context import (
    CHARS_PER_TOKEN,
    EN_DASH,
    NONE,
    MeetingContext,
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


def note_prompt(
    context: MeetingContext,
    *,
    template: Template,
    schema: Mapping[str, Any],
    language: str = "English",
) -> NotePrompt:
    """A1 on a meeting's shared context: the context is the system message, the task the user's."""
    task = load_part("a1_note")
    shown = replace(template, sections=template.synthesis_sections())
    user = task.render(
        output_language=language,
        schema=json.dumps(schema, separators=(",", ":")),
        template_name=template.name,
        template_sections_yaml=shown.sections_yaml(),
    )
    return NotePrompt(
        system=context.system,
        user=user,
        prompt_version=f"{context.version}+{task.version}",
        aliases=context.aliases,
        estimated_tokens=estimate_tokens(context.system + user),
    )


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
    return note_prompt(context, template=template, schema=schema, language=language)
