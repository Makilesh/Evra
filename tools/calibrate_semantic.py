"""Meaning-check calibration (BUILD.md §7.5): how well the embedding cosine tells the lines a
note point cites from lines it doesn't, and what it would do with the points the word check drops.

    uv run python tools/calibrate_semantic.py gemma4:12b

For both synthetic note fixtures the model writes the note with the meaning check off. Then every
pair below is embedded in one batch, the point as the query (with Evra's instruction), as the
meaning check scores it:

  supported    a kept point and the lines it cites
  mismatched   a kept point and 3 random lines neither cited nor within 3 lines of a cited one
               (random.Random(7))
  unsupported  a point the word check dropped as unsupported and the lines it cites

Prints p5/p50/p95 (and the extremes) per group, the share of each group at or above each
candidate threshold, the
threshold the rule picks (the smallest at which at most 2% of mismatched pairs pass) and every
unsupported point with its cosine, what the numbers-and-names check would then say, and the text
it cites. Synthetic fixtures only (BUILD.md §9.3).
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from evra.config import LlmSettings
from evra.console import safe_console
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import LlmProvider
from evra.llm.schemas import NoteBullet, NoteDraft
from evra.notes.context import MeetingContext, build_context
from evra.notes.semantic import Embedder, SemanticCheck
from evra.notes.structured import parse_reply
from evra.notes.templates import load_template
from evra.notes.validate import NEARBY, Grounder
from evra.notes.writer import write_note
from evra.store.meetings import Utterance

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # `tools` when run as a script

from tools.bakeoff_ask import Recorder
from tools.bakeoff_notes import FIXTURES, Case, load_case

Group = Literal["supported", "mismatched", "unsupported"]
GROUPS: tuple[Group, ...] = ("supported", "mismatched", "unsupported")
THRESHOLDS = (0.55, 0.60, 0.65, 0.70, 0.75)
MAX_MISMATCHED = 0.02  # the rule: at most 2% of mismatched pairs may pass
MISMATCHES = 3  # random far lines per kept point
SEED = 7
FIXTURE_NAMES = ("one_on_one_synthetic", "one_on_one_60min_synthetic")


@dataclass(frozen=True)
class Pair:
    group: Group
    case: str
    claim: str
    source: str
    bullet: NoteBullet


@dataclass(frozen=True)
class NoteCount:
    case: str
    kept: int
    unsupported: int
    other: Counter[str]


def far_lines(
    utterances: Sequence[Utterance], cited: Collection[str], rng: random.Random, count: int
) -> list[str]:
    """Up to `count` random lines that are neither cited nor within NEARBY lines of one."""
    ordered = sorted(utterances, key=lambda u: (u.start_ms, u.seq))
    near = {
        i + d for i, u in enumerate(ordered) if u.id in cited for d in range(-NEARBY, NEARBY + 1)
    }
    pool = [u.text for i, u in enumerate(ordered) if i not in near]
    return rng.sample(pool, min(count, len(pool)))


def percentile(values: Sequence[float], share: float) -> float:
    """Linear interpolation between the closest ranks (share 0.5 is the median)."""
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = share * (len(ordered) - 1)
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def share_at_or_above(values: Sequence[float], threshold: float) -> float:
    return sum(v >= threshold for v in values) / len(values) if values else 0.0


def pick_threshold(mismatched: Sequence[float]) -> float | None:
    """The smallest candidate threshold at which at most 2% of mismatched pairs pass."""
    return next((t for t in THRESHOLDS if share_at_or_above(mismatched, t) <= MAX_MISMATCHED), None)


def note_pairs(
    case: Case, draft: NoteDraft, rng: random.Random
) -> tuple[list[Pair], NoteCount, MeetingContext]:
    """The pairs one note gives, checked as the app checks it (by words only)."""
    context = build_context(meeting=case.meeting, utterances=case.utterances)
    grounder = Grounder(aliases=context.aliases, utterance_text=context.utterance_text)
    bullets = [*draft.summary, *(b for s in draft.sections for b in s.bullets)]
    pairs: list[Pair] = []
    kept = unsupported = 0
    other: Counter[str] = Counter()
    for bullet in bullets:
        checked, reason = grounder.check(bullet)
        pair = grounder.meaning_pair(bullet)
        if checked is not None and pair is not None:
            kept += 1
            claim, source = pair
            pairs.append(Pair("supported", case.name, claim, source, bullet))
            for line in far_lines(case.utterances, checked.citations, rng, MISMATCHES):
                pairs.append(Pair("mismatched", case.name, claim, line, bullet))
        elif reason == "unsupported" and pair is not None:
            unsupported += 1
            pairs.append(Pair("unsupported", case.name, *pair, bullet))
        else:
            other[reason] += 1
    return pairs, NoteCount(case.name, kept, unsupported, other), context


def _row(group: Group, scores: Sequence[float]) -> str:
    cells = " | ".join(f"{percentile(scores, p):.3f}" for p in (0.05, 0.5, 0.95, 0.0, 1.0))
    return f"| {group} | {len(scores)} | {cells} |"


def _count(scores: Sequence[float], threshold: float) -> str:
    hits = sum(s >= threshold for s in scores)
    return f"{hits}/{len(scores)} ({share_at_or_above(scores, threshold):.1%})"


def calibrate(
    provider: LlmProvider, model: str, cases: Sequence[Case], settings: LlmSettings
) -> list[str]:
    """Write each case's note (meaning check off), embed every pair in one batch, report."""
    recorder = Recorder(provider)
    rng = random.Random(SEED)
    pairs: list[Pair] = []
    counts: list[NoteCount] = []
    contexts: dict[str, MeetingContext] = {}
    for case in cases:
        write_note(
            recorder,
            model=model,
            meeting=case.meeting,
            utterances=case.utterances,
            template=load_template(str(case.meeting["template"])),
            settings=settings,
        )
        draft, _ = parse_reply(NoteDraft, recorder.replies[-1])  # the reply, or its repair
        assert draft is not None  # write_note raised otherwise
        found, count, contexts[case.name] = note_pairs(case, draft, rng)
        pairs += found
        counts.append(count)
    embedder = Embedder(provider, settings.embedding_model)
    scores = SemanticCheck(embedder).similarities([(p.claim, p.source) for p in pairs])
    by_group = {g: [s for p, s in zip(pairs, scores, strict=True) if p.group == g] for g in GROUPS}
    # what the numbers-and-names check says of a dropped point once its meaning lets it through
    # (a threshold of -1 lets every one through; the vectors are cached, so no new request)
    everything = SemanticCheck(embedder, threshold=-1.0)
    after: list[str] = []
    for pair in (p for p in pairs if p.group == "unsupported"):
        context = contexts[pair.case]
        again = Grounder(
            aliases=context.aliases, utterance_text=context.utterance_text, semantic=everything
        )
        checked, reason = again.check_all([pair.bullet])[0]
        after.append("kept" if checked is not None else reason)
    return _report(model, settings, counts, pairs, scores, by_group, after)


def _report(
    model: str,
    settings: LlmSettings,
    counts: Sequence[NoteCount],
    pairs: Sequence[Pair],
    scores: Sequence[float],
    by_group: dict[Group, list[float]],
    after: Sequence[str],
) -> list[str]:
    lines = [f"# Meaning check calibration: {model} notes, {settings.embedding_model}", ""]
    for c in counts:
        other = ", ".join(f"{r} {n}" for r, n in sorted(c.other.items())) or "none"
        lines.append(
            f"- {c.case}: {c.kept} points kept, {c.unsupported} unsupported,"
            f" {sum(c.other.values())} other drops ({other})"
        )
    lines += [
        "",
        "| group | pairs | p5 | p50 | p95 | min | max |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [_row(g, by_group[g]) for g in GROUPS]
    unsupported = [s for p, s in zip(pairs, scores, strict=True) if p.group == "unsupported"]
    lines += [
        "",
        "| threshold | mismatched at or above | supported at or above | unsupported at or above"
        " | unsupported then kept |",
        "| --- | --- | --- | --- | --- |",
    ]
    for t in THRESHOLDS:
        rescued = sum(s >= t and a == "kept" for s, a in zip(unsupported, after, strict=True))
        lines.append(
            f"| {t:.2f} | {_count(by_group['mismatched'], t)} | {_count(by_group['supported'], t)}"
            f" | {_count(unsupported, t)} | {rescued} |"
        )
    chosen = pick_threshold(by_group["mismatched"])
    lines += [
        "",
        "Rule: the smallest threshold at which at most 2% of mismatched pairs pass:"
        f" {'none' if chosen is None else f'{chosen:.2f}'}",
        "",
        "## Unsupported points (synthetic fixtures only)",
    ]
    dropped = [(p, s) for p, s in zip(pairs, scores, strict=True) if p.group == "unsupported"]
    for (pair, score), verdict in zip(dropped, after, strict=True):
        lines += [
            f"- {score:.3f} | if its meaning passes: {verdict} | {pair.case}",
            f"  point: {pair.claim}",
            f"  cites: {pair.source}",
        ]
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    safe_console()
    parser = argparse.ArgumentParser(description="Calibrate the meaning check's threshold")
    parser.add_argument("model", help="the note model, e.g. gemma4:12b")
    args = parser.parse_args(argv)
    settings = LlmSettings(keep_alive="5m")
    cases = [load_case(FIXTURES / f"{name}.json") for name in FIXTURE_NAMES]
    for line in calibrate(OllamaProvider(settings), args.model, cases, settings):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
