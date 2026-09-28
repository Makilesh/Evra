"""Note-model bake-off (BUILD.md D4, §7.4): the same inputs through several Ollama models.

    uv run python tools/bakeoff_notes.py gemma4:12b qwen3.5:9b ministral-3:14b --runs 2
    uv run python tools/bakeoff_notes.py qwen3.5:9b --think
    uv run python tools/bakeoff_notes.py gemma4:12b --meeting-id <id> --show   # a real meeting

Real-meeting output stays on this console; never commit it (BUILD.md §9.3).
Columns: validity = kept / (kept + dropped); coverage = expected facts found in kept points;
on GPU = share of the loaded model in VRAM (from Ollama's /api/ps).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from evra.config import LlmSettings
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import LlmError, LlmProvider
from evra.notes.templates import load_template
from evra.notes.validate import CheckedNote
from evra.notes.writer import NoteError, write_note
from evra.paths import resolve_paths
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "notes"


@dataclass(frozen=True)
class Expected:
    what: str
    keywords: tuple[str, ...]  # every keyword must appear; "a|b" means either


@dataclass(frozen=True)
class Case:
    name: str
    meeting: dict[str, Any]
    utterances: list[Utterance]
    expected: tuple[Expected, ...]


@dataclass(frozen=True)
class Row:
    model: str
    case: str
    seconds: float
    tokens_in: int
    tokens_out: int
    repaired: bool
    kept: int
    dropped: int
    coverage: float | None
    gpu_share: float | None
    error: str = ""

    @property
    def validity(self) -> float:
        total = self.kept + self.dropped
        return self.kept / total if total else 0.0


def load_case(path: Path) -> Case:
    data = json.loads(path.read_text(encoding="utf-8"))
    utterances = [
        Utterance(
            f"{path.stem}-{i}",
            "fixture",
            path.stem,
            i,
            u["ch"],
            None,
            u["start_ms"],
            u["end_ms"],
            u["text"],
            (),
            None,
        )
        for i, u in enumerate(data["utterances"])
    ]
    meeting = {
        "id": path.stem,
        "title": data["title"],
        "started_at": data["started_at"],
        "situation": data["situation"],
        "template": data["template"],
    }
    expected = tuple(Expected(e["what"], tuple(e["keywords"])) for e in data["expected"])
    return Case(path.stem, meeting, utterances, expected)


def meeting_case(meeting_id: str) -> Case:
    conn = connect(resolve_paths().db_path)
    try:
        store = MeetingStore(conn)
        meeting = store.get_meeting(meeting_id)
        version = store.current_transcript_version(meeting_id)
        utterances = store.utterances(version) if version else []
    finally:
        conn.close()
    return Case(meeting_id[:8], meeting, utterances, ())


def covered(note: CheckedNote, fact: Expected) -> bool:
    texts = [b.text.lower() for b in note.summary]
    texts += [b.text.lower() for s in note.sections for b in s.bullets]
    return any(
        all(any(alt in text for alt in keyword.lower().split("|")) for keyword in fact.keywords)
        for text in texts
    )


def run_case(
    provider: LlmProvider, model: str, case: Case, settings: LlmSettings, *, show: bool = False
) -> Row:
    template = load_template(str(case.meeting["template"]))
    try:
        result = write_note(
            provider,
            model=model,
            meeting=case.meeting,
            utterances=case.utterances,
            template=template,
            settings=settings,
        )
    except (LlmError, NoteError) as exc:
        return Row(model, case.name, 0.0, 0, 0, False, 0, 0, None, None, type(exc).__name__)
    note = result.note
    if show:
        print(f"\n### {model} - {case.name}")
        for bullet in note.summary:
            print(f"- {bullet.text}")
        for section in note.sections:
            print(f"## {section.title}")
            for bullet in section.bullets:
                print(f"- {bullet.text}")
    coverage = (
        sum(covered(note, f) for f in case.expected) / len(case.expected) if case.expected else None
    )
    return Row(
        model,
        case.name,
        result.seconds,
        result.tokens_in,
        result.tokens_out,
        result.repaired,
        note.kept,
        note.dropped,
        coverage,
        None,
    )


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def format_table(rows: Sequence[Row]) -> list[str]:
    lines = [
        "| model | case | seconds | tokens in/out | repaired | kept | dropped | validity"
        " | coverage | on GPU | error |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r.model} | {r.case} | {r.seconds:.1f} | {r.tokens_in}/{r.tokens_out}"
            f" | {'yes' if r.repaired else 'no'} | {r.kept} | {r.dropped}"
            f" | {_pct(r.validity if not r.error else None)} | {_pct(r.coverage)}"
            f" | {_pct(r.gpu_share)} | {r.error} |"
        )
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Ollama models on note writing")
    parser.add_argument("models", nargs="+")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--think", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--meeting-id", default=None, help="a stored meeting instead of fixtures")
    parser.add_argument("--show", action="store_true", help="print each note (console only)")
    args = parser.parse_args(argv)
    if args.meeting_id:
        cases = [meeting_case(args.meeting_id)]
    else:
        cases = [load_case(p) for p in sorted(FIXTURES.glob("*.json"))]
    settings = LlmSettings(think=args.think, keep_alive="5m")
    provider = OllamaProvider(settings)
    rows: list[Row] = []
    for model in args.models:
        for case in cases:
            for _ in range(args.runs):
                row = run_case(provider, model, case, settings, show=args.show)
                share = None
                with contextlib.suppress(LlmError):
                    share = provider.gpu_share(model)
                rows.append(replace(row, gpu_share=share))
                print(
                    f"{model} {case.name}: {row.error or 'ok'} in {row.seconds:.1f} s", flush=True
                )
        with contextlib.suppress(LlmError):  # unload: one model in VRAM at a time
            provider.unload(model)
    print()
    for line in format_table(rows):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
