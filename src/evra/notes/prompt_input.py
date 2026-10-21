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
from evra.notes.templates import Template
from evra.store.meetings import Utterance
from evra.transcribe.cli import format_ms
from evra.transcribe.labels import PARTICIPANTS_1ON1, speaker_label

CHARS_PER_TOKEN = 3.5  # conservative for English; Ollama's real count is recorded afterwards
NONE = "(none)"
LOOKALIKE_LT, LOOKALIKE_GT = chr(0x2039), chr(0x203A)  # single angle quotation marks
EN_DASH = chr(0x2013)


@dataclass(frozen=True)
class NotePrompt:
    system: str
    user: str
    prompt_version: str
    aliases: Mapping[str, str]  # "u:3" -> utterance id
    estimated_tokens: int


def as_data(text: str) -> str:
    """Angle brackets become look-alikes so data can never open or close a prompt tag."""
    return text.replace("<", LOOKALIKE_LT).replace(">", LOOKALIKE_GT)


def _one_line(text: str) -> str:
    return " ".join(as_data(text).split())


def transcript_lines(utterances: Sequence[Utterance]) -> tuple[str, dict[str, str]]:
    lines: list[str] = []
    aliases: dict[str, str] = {}
    ordered = sorted(utterances, key=lambda u: (u.start_ms, u.seq))
    for n, u in enumerate(ordered, start=1):
        alias = f"u:{n}"
        aliases[alias] = u.id
        lines.append(
            f"[{alias}] [{format_ms(u.start_ms)}] {speaker_label(u.channel)}: {_one_line(u.text)}"
        )
    return "\n".join(lines), aliases


def _gap_lines(gaps: Sequence[Mapping[str, Any]]) -> str:
    lines = []
    for gap in gaps:
        start, end = format_ms(int(gap["start_ms"])), format_ms(int(gap["end_ms"]))
        lines.append(f"GAP {start}{EN_DASH}{end} ({_one_line(str(gap['cause']))})")
    return "\n".join(lines) or NONE


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
