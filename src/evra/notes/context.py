"""One system message per meeting (A0): the transcript first, because it never changes once a
call ends, then the user's notes, gaps and metadata. Every call about a meeting (the note,
questions) sends this same text, so Ollama can reuse the prompt it already processed. Once the
owner says who a 1:1 was with, its participants name them (C6); the transcript keeps "Them"."""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from evra.llm.prompt_files import load_part
from evra.store.meetings import Utterance
from evra.store.speakers import THEM
from evra.transcribe.cli import format_ms
from evra.transcribe.labels import PARTICIPANTS_1ON1, speaker_label

# Measured on gemma4:12b: transcript lines run ~2.7 characters a token (their ids and times are
# digits), the rules' prose ~3.4. The transcript rate keeps long calls, where it matters, exact.
CHARS_PER_TOKEN = 2.7
NONE = "(none)"
ELLIPSIS = chr(0x2026)
EXCERPT_NOTE = (
    "Only the parts of the meeting that best match the question are shown; "
    f"{ELLIPSIS} marks lines left out.\n"
)
LOOKALIKE_LT, LOOKALIKE_GT = chr(0x2039), chr(0x203A)  # single angle quotation marks
EN_DASH = chr(0x2013)


@dataclass(frozen=True)
class MeetingContext:
    system: str
    version: str
    aliases: Mapping[str, str]  # "u:3" -> utterance id, over the whole meeting
    utterance_text: Mapping[str, str]  # every utterance id -> text
    estimated_tokens: int
    excerpt: bool
    # the transcript's labels mapped to who they stand for ({"Them": "Priya"}), so every call
    # built on this context reads and checks the same names
    names: Mapping[str, str] = MappingProxyType({})


def as_data(text: str) -> str:
    """Angle brackets become look-alikes so data can never open or close a prompt tag."""
    return text.replace("<", LOOKALIKE_LT).replace(">", LOOKALIKE_GT)


def _one_line(text: str) -> str:
    return " ".join(as_data(text).split())


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _in_time_order(utterances: Sequence[Utterance]) -> list[Utterance]:
    return sorted(utterances, key=lambda u: (u.start_ms, u.seq))


def line_aliases(utterances: Sequence[Utterance]) -> dict[str, str]:
    """u:1..u:N -> utterance id, numbered as `transcript_lines` numbers them."""
    return {f"u:{n}": u.id for n, u in enumerate(_in_time_order(utterances), start=1)}


def transcript_lines(
    utterances: Sequence[Utterance], only: Collection[str] | None = None
) -> tuple[str, dict[str, str]]:
    """Every utterance is numbered u:1..u:N in time order; with `only`, just those are printed,
    and a line of an ellipsis stands wherever printed lines skip over left-out ones."""
    lines: list[str] = []
    aliases: dict[str, str] = {}
    skipped = False
    for n, u in enumerate(_in_time_order(utterances), start=1):
        alias = f"u:{n}"
        aliases[alias] = u.id
        if only is not None and u.id not in only:
            skipped = True
            continue
        if skipped:
            lines.append(ELLIPSIS)
            skipped = False
        lines.append(
            f"[{alias}] [{format_ms(u.start_ms)}] {speaker_label(u.channel)}: {_one_line(u.text)}"
        )
    if skipped:
        lines.append(ELLIPSIS)
    return "\n".join(lines), aliases


def participants(names: Mapping[str, str]) -> str:
    """Who was on the call: the other person by name once the owner has said who the 1:1 was
    with, and how the transcript calls them."""
    person = names.get(THEM)
    if not person:
        return PARTICIPANTS_1ON1
    return (
        f"You (the owner of this note), {_one_line(person)}"
        f' (the other person on the call; "{THEM}" in the transcript)'
    )


def _gap_lines(gaps: Sequence[Mapping[str, Any]]) -> str:
    lines = []
    for gap in gaps:
        start, end = format_ms(int(gap["start_ms"])), format_ms(int(gap["end_ms"]))
        lines.append(f"GAP {start}{EN_DASH}{end} ({_one_line(str(gap['cause']))})")
    return "\n".join(lines) or NONE


def build_context(
    *,
    meeting: Mapping[str, Any],
    utterances: Sequence[Utterance],
    gaps: Sequence[Mapping[str, Any]] = (),
    user_notes: str = NONE,
    only: Collection[str] | None = None,
    note: str | None = None,
    names: Mapping[str, str] | None = None,
) -> MeetingContext:
    """`note` is the text placed before the transcript lines (a long call's part says which part
    it is); with `only` and no note, it is the excerpt note. `names` maps the transcript's
    labels to who they stand for ({"Them": "Priya"}): the participants name them."""
    named = MappingProxyType(dict(names or {}))
    if not utterances:
        raise ValueError("no utterances")
    part = load_part("a0_context")
    transcript, aliases = transcript_lines(utterances, only)
    end_ms = max(u.end_ms for u in utterances)
    started = datetime.fromtimestamp(int(meeting["started_at"]) / 1000)
    if note is None:
        note = EXCERPT_NOTE if only is not None else ""
    system = part.render(
        excerpt_note=note,
        transcript=transcript,
        gaps=_gap_lines(gaps),
        user_notes=user_notes,
        title=_one_line(str(meeting["title"])),
        date_iso=started.date().isoformat(),
        duration_minutes=str(max(1, round(end_ms / 60_000))),
        setting=_one_line(str(meeting.get("situation") or "unknown").replace("_", " ")),
        participants=participants(named),
    )
    return MeetingContext(
        system=system,
        version=part.version,
        aliases=aliases,
        utterance_text={u.id: u.text for u in utterances},
        estimated_tokens=estimate_tokens(system),
        excerpt=only is not None,
        names=named,
    )
