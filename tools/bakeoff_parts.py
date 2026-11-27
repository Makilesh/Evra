"""Long calls in the note bake-off (A2/A3): the 60-minute synthetic call cut after its first
minutes, the way a note is written forced through `llm.single_pass_minutes`, and what each
part and the combining call took.

    uv run python tools/bakeoff_notes.py gemma4:12b --runs 2 --minutes 15,30,45,60 --path windows
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from evra.config import LlmSettings
from evra.notes.extract import Extraction
from evra.notes.job import generation_version
from evra.notes.writer import NoteResult

if TYPE_CHECKING:  # tools.bakeoff_notes imports this module
    from tools.bakeoff_notes import Case

ForcedPath = Literal["auto", "single", "windows"]
PATHS: tuple[ForcedPath, ...] = ("auto", "single", "windows")
LONG_FIXTURE = "one_on_one_60min_synthetic.json"
NEVER_MINUTES = 7 * 24 * 60  # no call lasts a week
# how each call's last message starts: a part (A2), the combining call (A3), a repair (A9)
PART_TASK = "Summarise this part of the meeting"
COMBINE_TASK = "Write the note for the meeting above from the summaries of its parts"
REPAIR_TASK = "<schema>"


def cut_case(case: Case, minutes: int) -> Case:
    """The call's first `minutes`: the lines that start before the cut, and the facts planted
    before it."""
    cut_ms = minutes * 60_000
    return replace(
        case,
        name=f"{case.name}-{minutes}m",
        utterances=[u for u in case.utterances if u.start_ms < cut_ms],
        expected=tuple(f for f in case.expected if f.minute is not None and f.minute < minutes),
    )


def cut_cases(case: Case, minutes: str) -> list[Case]:
    """`minutes` as "15,30,45,60"."""
    return [cut_case(case, int(m)) for m in minutes.split(",") if m.strip()]


def path_settings(settings: LlmSettings, path: ForcedPath) -> LlmSettings:
    """`auto` as the app chooses; `windows` reads every call in parts; `single` never chooses
    parts for a call's length (a prompt over the budget still goes in parts: one pass can't
    read it)."""
    if path == "auto":
        return settings
    minutes = 0 if path == "windows" else NEVER_MINUTES
    return settings.model_copy(update={"single_pass_minutes": minutes})


def taken_path(result: NoteResult, extraction: Extraction) -> str:
    """How the note was written, from its version: a2 means in parts."""
    parts = generation_version(result, extraction).split("+")
    return "windows" if any(p.startswith("a2-") for p in parts) else "single"


@dataclass(frozen=True)
class PartCalls:
    part_seconds: tuple[float, ...]  # each part's call (A2), with its repair
    combine_seconds: float | None  # the combining call (A3), with its repair
    combine_tokens: int | None  # A3's reply in tokens, with its repair's


def part_calls(calls: Sequence[tuple[str, float, int]]) -> PartCalls:
    """What each part and the combining call took, from the recorded calls: (how its last
    message starts, seconds, reply tokens)."""
    parts: list[float] = []
    combine: float | None = None
    combine_tokens: int | None = None
    last = ""
    for task, seconds, tokens in calls:
        if task.startswith(REPAIR_TASK):
            if last == "part":
                parts[-1] += seconds
            elif last == "combine":
                combine = (combine or 0.0) + seconds
                combine_tokens = (combine_tokens or 0) + tokens
            continue
        last = ""
        if task.startswith(PART_TASK):
            parts.append(seconds)
            last = "part"
        elif task.startswith(COMBINE_TASK):
            combine, combine_tokens = seconds, tokens
            last = "combine"
    return PartCalls(tuple(parts), combine, combine_tokens)
