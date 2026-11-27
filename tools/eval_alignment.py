"""Notepad alignment against labelled lines (BUILD.md §7.2): the twelve lines an owner might type
during the 60-minute synthetic call (`tools/notes_fixture.py`), each labelled with the transcript
lines it was written about, linked as the note job links them (`evra.notes.align`).

    uv run python tools/eval_alignment.py              # with meaning (Ollama, embedding model)
    uv run python tools/eval_alignment.py --no-embed   # by time and words alone
    uv run python tools/eval_alignment.py --sweep --show

Precision = linked lines that are labelled / every linked line; recall = labelled lines that are
linked / every labelled line, over all twelve, at the cut-off of the mode (MIN_SCORE with
meaning, MIN_SCORE_NO_MEANING without). §7.2's acceptance: precision >= 0.80 at recall >= 0.60,
and a 60-minute meeting with 50 note lines links in under 5 s. The twelve are linked first with
the embedding model unloaded (its load counted), then again warm on a fresh embedder; then 50
lines spread over the call are linked on a fresh embedder, as the note job links them.
`--sweep` shows precision and recall at other cut-offs (the score and the most lines kept per
note), from every candidate, none left out before the batch; `--show` each line's candidates.
Synthetic fixtures only.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from evra.config import LlmSettings
from evra.console import safe_console
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import LlmError
from evra.notes.align import (
    MAX_PER_LINE,
    MIN_SCORE,
    MIN_SCORE_NO_MEANING,
    Candidate,
    best,
    candidates,
)
from evra.notes.semantic import Embedder
from evra.store.notepad import NoteLine
from evra.transcribe.cli import format_ms

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # `tools` when run as a script

from tools.bakeoff_notes import FIXTURES, Case, load_case
from tools.bakeoff_parts import LONG_FIXTURE
from tools.notes_fixture import NOTES_FIXTURE, load_notes

TIMED_LINES = 50  # §7.2: "a 60-minute meeting with 50 note lines aligns in < 5 s"
CUT_OFFS = (0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70)
MOST = (1, 2, 3, MAX_PER_LINE)


@dataclass(frozen=True)
class Score:
    kept: int  # lines linked, over every note
    labelled: int
    hits: int  # linked and labelled

    @property
    def precision(self) -> float | None:
        return self.hits / self.kept if self.kept else None

    @property
    def recall(self) -> float:
        return self.hits / self.labelled if self.labelled else 0.0


def score(
    linked: Mapping[str, Sequence[tuple[str, float]]], about: Mapping[str, frozenset[str]]
) -> Score:
    kept = labelled = hits = 0
    for line_id, wanted in about.items():
        got = {uid for uid, _ in linked.get(line_id, ())}
        kept, labelled, hits = kept + len(got), labelled + len(wanted), hits + len(got & wanted)
    return Score(kept, labelled, hits)


def spread(lines: Sequence[NoteLine], count: int, length_ms: int) -> list[NoteLine]:
    """`count` lines evenly over a call of `length_ms`, their texts taken from `lines` in turn."""
    return [
        replace(
            lines[k % len(lines)],
            id=f"t{k}",
            position=k,
            captured_at_ms=round((k + 0.5) * length_ms / count),
        )
        for k in range(count)
    ]


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def _row(name: str, result: Score) -> str:
    return (
        f"| {name} | {result.kept} | {result.labelled} | {result.hits}"
        f" | {_pct(result.precision)} | {_pct(result.recall)} |"
    )


def _sweep(found: Mapping[str, Sequence[Candidate]], about: Mapping[str, frozenset[str]]) -> None:
    print("\n| score at least, most per note | linked | labelled | right | precision | recall |")
    print("| --- | --- | --- | --- | --- | --- |")
    for cut in CUT_OFFS:
        for most in MOST:
            linked = {k: best(c, min_score=cut, most=most) for k, c in found.items()}
            print(_row(f"{cut:.2f}, {most}", score(linked, about)))


def _show(
    lines: Sequence[NoteLine],
    found: Mapping[str, Sequence[Candidate]],
    about: Mapping[str, frozenset[str]],
    starts: Mapping[str, int],
) -> None:
    for line in lines:
        assert line.captured_at_ms is not None
        print(f"\n{line.id} [{format_ms(line.captured_at_ms)}] {line.text}")
        kept = {uid for uid, _ in best(found[line.id])}
        for c in sorted(found[line.id], key=lambda c: -c.score)[:8]:
            mark = ("linked " if c.utterance_id in kept else "       ") + (
                "labelled" if c.utterance_id in about[line.id] else ""
            )
            meaning = "-" if c.w_sem is None else f"{c.w_sem:.2f}"
            print(
                f"  [{format_ms(starts[c.utterance_id])}] {c.score:.2f} = time {c.w_time:.2f},"
                f" words {c.w_lex:.2f}, meaning {meaning}  {mark}"
            )


def _timed(lines: Sequence[NoteLine], case: Case, embedder: Embedder | None) -> float:
    started = time.monotonic()
    candidates(lines, case.utterances, embedder=embedder)
    return time.monotonic() - started


def main(argv: Sequence[str] | None = None) -> int:
    safe_console()
    parser = argparse.ArgumentParser(description="Notepad alignment against labelled lines")
    parser.add_argument("--no-embed", action="store_true", help="link by time and words alone")
    parser.add_argument("--sweep", action="store_true", help="other cut-offs")
    parser.add_argument("--show", action="store_true", help="each line's candidates")
    args = parser.parse_args(argv)
    case = load_case(FIXTURES / LONG_FIXTURE)
    notes = load_notes(NOTES_FIXTURE, case.utterances)
    settings = LlmSettings()
    provider = OllamaProvider(settings)

    def embedder() -> Embedder | None:
        return None if args.no_embed else Embedder(provider, settings.embedding_model)

    if not args.no_embed:  # the first run pays for loading the embedding model
        with contextlib.suppress(LlmError):
            provider.unload(settings.embedding_model)
    how = "time and words alone" if args.no_embed else f"with meaning, {settings.embedding_model}"
    cut = MIN_SCORE_NO_MEANING if args.no_embed else MIN_SCORE
    print(f"Notepad alignment: {len(notes.lines)} typed lines of {LONG_FIXTURE} ({how})")
    print(f"kept: score at least {cut:.2f}, at most {MAX_PER_LINE} per note\n")
    started = time.monotonic()
    found = candidates(notes.lines, case.utterances, embedder=embedder())
    seconds = time.monotonic() - started
    linked = {line_id: best(c) for line_id, c in found.items()}
    print("| run | linked | labelled | right | precision | recall |")
    print("| --- | --- | --- | --- | --- | --- |")
    print(_row("kept", score(linked, notes.about)))
    twelve = len(notes.lines)
    first = "first" if args.no_embed else "the embedding model loaded first"
    print(f"\n{twelve} lines linked in {seconds:.2f} s, {first}")
    print(f"{twelve} lines linked in {_timed(notes.lines, case, embedder()):.2f} s, warm")
    timed = spread(notes.lines, TIMED_LINES, max(u.end_ms for u in case.utterances))
    print(f"{TIMED_LINES} lines over the call linked in {_timed(timed, case, embedder()):.2f} s")
    if args.sweep or args.show:
        every = candidates(
            notes.lines, case.utterances, embedder=embedder(), at_least=min(CUT_OFFS)
        )
        if args.sweep:
            _sweep(every, notes.about)
        if args.show:
            _show(notes.lines, every, notes.about, {u.id: u.start_ms for u in case.utterances})
    return 0


if __name__ == "__main__":
    sys.exit(main())
