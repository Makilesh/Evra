"""Note-model bake-off (BUILD.md D4, §7.4): the same inputs through several Ollama models, each
note written the way the window writes it (the note's own sections with A1, then its action
items, decisions and open questions with A4-A6, checked by words and by meaning; a long call in
parts, A2, then combined, A3).

    uv run python tools/bakeoff_notes.py gemma4:12b qwen3.5:9b ministral-3:14b --runs 2
    uv run python tools/bakeoff_notes.py qwen3.5:9b --think
    uv run python tools/bakeoff_notes.py gemma4:12b --meeting-id <id> --show   # a real meeting
    uv run python tools/bakeoff_notes.py gemma4:12b --minutes 15,30,45,60 --path windows

Real-meeting output stays on this console; never commit it (BUILD.md §9.3).
Columns: path = how the note was written (`--path` forces it: auto, single or windows);
seconds = the note's own calls (A1; or every part and A3), in all = from the first call to the
checked note and its lists; parts s and A3 s = each part's call and the combining call;
validity = kept / (kept + dropped), the note's own points; rescued = points the meaning check
kept; coverage = expected facts found in one kept point; with items = found in one point or one
item; items = action items / decisions / open questions kept; removed r/a = items A3 removed as
repeats / as questions answered later; dup facts = facts found in two items of one kind;
commitments = planted tasks found in one action item (its owner, text and due date as shown);
on GPU = share of the loaded model in VRAM (from Ollama's /api/ps). After each run come the
points the check dropped, with their reasons and the lines they cite. `--minutes` cuts the
60-minute call after its first minutes and counts only the facts planted before each cut.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from evra.config import LlmSettings
from evra.console import safe_console
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import ChatMessage, ChatResult, LlmError, LlmProvider
from evra.llm.schemas import NoteBullet, NoteDraft
from evra.notes.context import build_context
from evra.notes.extract import CheckedItem, Extraction
from evra.notes.job import write_note_and_items
from evra.notes.semantic import Embedder, SemanticCheck
from evra.notes.structured import parse_reply
from evra.notes.templates import Template, load_template
from evra.notes.validate import CheckedNote, Grounder
from evra.notes.writer import NoteError, NoteResult, synthesis_only
from evra.paths import resolve_paths
from evra.services.views import item_text
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # `tools` when run as a script

from tools.bakeoff_parts import (
    LONG_FIXTURE,
    PATHS,
    call_seconds,
    cut_cases,
    path_settings,
    taken_path,
)

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "notes"


@dataclass(frozen=True)
class Expected:
    what: str
    keywords: tuple[str, ...]  # every keyword must appear; "a|b" means either
    commitment: bool = False  # a task someone took on: it belongs in one action item
    minute: int | None = None  # when it is said (the 60-minute call's facts)


@dataclass(frozen=True)
class Case:
    name: str
    meeting: dict[str, Any]
    utterances: list[Utterance]
    expected: tuple[Expected, ...]


@dataclass(frozen=True)
class Dropped:
    text: str
    reason: str
    cited: tuple[str, ...]  # "u:12: what that line says"


@dataclass(frozen=True)
class Row:
    model: str
    case: str
    seconds: float  # the note's own call (A1, with its repair)
    tokens_in: int
    tokens_out: int
    repaired: bool
    kept: int
    dropped: int
    coverage: float | None  # facts in the note's own points
    gpu_share: float | None
    error: str = ""
    rescued: int = 0
    total_seconds: float = 0.0  # from the first call to the checked note and its lists
    items: tuple[int, int, int] = (0, 0, 0)  # action items, decisions, open questions
    with_items: float | None = None  # facts in a point or an item
    commitments: tuple[int, int] | None = None  # found in one action item, planted
    reasons: Mapping[str, int] = field(default_factory=dict)  # the note check's drops
    drops: tuple[Dropped, ...] = ()
    tasks_as_decisions: int = 0  # decisions left out as repeats of an action item
    path: str = ""  # "single" or "windows"
    part_seconds: tuple[float, ...] = ()  # each part's call (A2)
    combine_seconds: float | None = None  # the combining call (A3)
    removed: tuple[int, int] = (0, 0)  # A3 removed: repeats, questions answered later
    duplicates: int = 0  # facts found in two items of one kind

    @property
    def validity(self) -> float:
        total = self.kept + self.dropped
        return self.kept / total if total else 0.0


class Recorder:
    """Passes calls on and keeps the replies, so the model's own answer can be scored before
    the transcript check drops anything."""

    def __init__(self, inner: LlmProvider) -> None:
        self.inner = inner
        self.name = inner.name
        self.replies: list[str] = []
        self.calls: list[tuple[str, float]] = []  # how each call's task starts, and its seconds

    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        result = self.inner.chat_json(model, messages, schema)
        self.replies.append(result.content)
        self.calls.append((messages[-1].content[:80], result.seconds))
        return result

    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        return self.inner.embed(model, texts)

    def installed_models(self) -> list[str]:
        return self.inner.installed_models()

    def load(self, model: str) -> None:
        self.inner.load(model)


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
    expected = tuple(
        Expected(e["what"], tuple(e["keywords"]), bool(e.get("commitment", False)), e.get("minute"))
        for e in data["expected"]
    )
    return Case(path.stem, meeting, utterances, expected)


HOUR_MS = 3_600_000


def repeat_case(case: Case, hours: int) -> Case:
    """The call said `hours` times over, each copy an hour after the one before: the 60-minute
    fixture becomes a 2-hour call, too long to read whole, with every fact said twice."""
    if hours <= 1:
        return case
    n = len(case.utterances)
    utterances = [
        replace(
            u,
            id=u.id if k == 0 else f"{u.id}-h{k}",
            seq=u.seq + k * n,
            start_ms=u.start_ms + k * HOUR_MS,
            end_ms=u.end_ms + k * HOUR_MS,
        )
        for k in range(hours)
        for u in case.utterances
    ]
    return replace(case, name=f"{case.name}-{hours}h", utterances=utterances)


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


def _holds(text: str, fact: Expected) -> bool:
    text = text.lower()
    return all(any(alt in text for alt in k.lower().split("|")) for k in fact.keywords)


def covered(note: CheckedNote, fact: Expected) -> bool:
    texts = [b.text for b in note.summary] + [b.text for s in note.sections for b in s.bullets]
    return any(_holds(text, fact) for text in texts)


def shown(item: CheckedItem) -> str:
    """An item as the note shows it."""
    return item_text(item.kind, item.owner, item.text, item.due)


def in_items(items: Sequence[CheckedItem], fact: Expected, *, kind: str | None = None) -> bool:
    return any(_holds(shown(i), fact) for i in items if kind is None or i.kind == kind)


def surviving_duplicates(items: Sequence[CheckedItem], facts: Sequence[Expected]) -> int:
    """Facts found in two items of one kind: a repeat that the merge and A3 left."""
    kinds = {i.kind for i in items}
    return sum(
        any(sum(_holds(shown(i), f) for i in items if i.kind == k) >= 2 for k in kinds)
        for f in facts
    )


def dropped_points(
    reply: str, case: Case, template: Template, semantic: SemanticCheck | None
) -> tuple[Dropped, ...]:
    """The note's own points the check dropped, why, and what they cite: the same check again on
    A1's reply (its embeddings are cached, so no new request)."""
    draft, _ = parse_reply(NoteDraft, reply)
    if draft is None:
        return ()
    own, _ = synthesis_only(draft, template)
    bullets: list[NoteBullet] = [*own.summary, *(b for s in own.sections for b in s.bullets)]
    context = build_context(meeting=case.meeting, utterances=case.utterances)
    grounder = Grounder(
        aliases=context.aliases, utterance_text=context.utterance_text, semantic=semantic
    )
    drops: list[Dropped] = []
    for bullet, (checked, reason) in zip(bullets, grounder.check_all(bullets), strict=True):
        if checked is not None:
            continue
        cited = tuple(
            f"{c}: {context.utterance_text[context.aliases[c]]}"
            for c in bullet.citations
            if c in context.aliases
        )
        drops.append(Dropped(bullet.text, reason, cited))
    return tuple(drops)


def _show(model: str, case: Case, result: NoteResult, extraction: Extraction) -> None:
    print(f"\n### {model} - {case.name}")
    for bullet in result.note.summary:
        print(f"- {bullet.text}")
    for section in result.note.sections:
        print(f"## {section.title}")
        for bullet in section.bullets:
            print(f"- {bullet.text}")
    for kind in ("action_item", "decision", "open_question"):
        found = [i for i in extraction.items if i.kind == kind]
        if found:
            print(f"## {kind.replace('_', ' ')}s")
            for item in found:
                print(f"- {shown(item)}")
    for fact in case.expected:
        where = [
            name
            for name, hit in (
                ("note", covered(result.note, fact)),
                ("items", in_items(extraction.items, fact)),
            )
            if hit
        ]
        print(f"  fact {fact.what!r}: {' and '.join(where) or 'missed'}")


def run_case(
    provider: LlmProvider, model: str, case: Case, settings: LlmSettings, *, show: bool = False
) -> Row:
    """The note as the window writes it, with the meaning check, scored."""
    template = load_template(str(case.meeting["template"]))
    recorder = Recorder(provider)
    semantic = SemanticCheck(Embedder(recorder, settings.embedding_model))
    started = time.monotonic()
    try:
        result, extraction = write_note_and_items(
            recorder,
            model=model,
            meeting=case.meeting,
            utterances=case.utterances,
            template=template,
            settings=settings,
            semantic=semantic,
        )
    except (LlmError, NoteError) as exc:
        return Row(model, case.name, 0.0, 0, 0, False, 0, 0, None, None, type(exc).__name__)
    total = time.monotonic() - started
    note = result.note
    path = taken_path(result, extraction)
    drops: tuple[Dropped, ...] = ()
    if not result.items_only:  # the reply the note came from (A1's or A3's), after any repair
        reply = recorder.replies[-1 if path == "windows" else int(result.repaired)]
        drops = dropped_points(reply, case, template, semantic)
    part_seconds, combine_seconds = call_seconds(recorder.calls)
    if show:
        _show(model, case, result, extraction)
    facts = case.expected
    planted = [f for f in facts if f.commitment]
    kinds = [i.kind for i in extraction.items]
    return Row(
        model,
        case.name,
        result.seconds,
        result.tokens_in,
        result.tokens_out,
        result.repaired,
        note.kept,
        note.dropped,
        sum(covered(note, f) for f in facts) / len(facts) if facts else None,
        None,
        rescued=note.rescued,
        total_seconds=total,
        items=(kinds.count("action_item"), kinds.count("decision"), kinds.count("open_question")),
        with_items=(
            sum(covered(note, f) or in_items(extraction.items, f) for f in facts) / len(facts)
            if facts
            else None
        ),
        commitments=(
            (sum(in_items(extraction.items, f, kind="action_item") for f in planted), len(planted))
            if planted
            else None
        ),
        reasons=dict(note.drop_reasons),
        drops=drops,
        tasks_as_decisions=extraction.tasks_as_decisions,
        path=path,
        part_seconds=part_seconds,
        combine_seconds=combine_seconds,
        removed=(extraction.repeats_removed, extraction.answered_removed),
        duplicates=surviving_duplicates(extraction.items, facts),
    )


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.0%}"


def format_table(rows: Sequence[Row]) -> list[str]:
    head = (
        "| model | case | path | seconds | in all | parts s | A3 s | tokens in/out | repaired"
        " | kept | dropped | rescued | validity | coverage | with items | items a/d/q"
        " | removed r/a | dup facts | commitments | on GPU | error |"
    )
    lines = [head, "|" + " --- |" * (head.count("|") - 1)]
    for r in rows:
        commitments = "-" if r.commitments is None else f"{r.commitments[0]}/{r.commitments[1]}"
        parts = "/".join(f"{s:.1f}" for s in r.part_seconds) or "-"
        combine = "-" if r.combine_seconds is None else f"{r.combine_seconds:.1f}"
        lines.append(
            f"| {r.model} | {r.case} | {r.path or '-'} | {r.seconds:.1f} | {r.total_seconds:.1f}"
            f" | {parts} | {combine} | {r.tokens_in}/{r.tokens_out}"
            f" | {'yes' if r.repaired else 'no'} | {r.kept} | {r.dropped} | {r.rescued}"
            f" | {_pct(r.validity if not r.error else None)} | {_pct(r.coverage)}"
            f" | {_pct(r.with_items)} | {'/'.join(map(str, r.items))}"
            f" | {r.removed[0]}/{r.removed[1]} | {r.duplicates} | {commitments}"
            f" | {_pct(r.gpu_share)} | {r.error} |"
        )
    return lines


def format_drops(row: Row) -> list[str]:
    """A run's dropped points with their reasons, and what each cites; then how many decisions
    were left out as repeats of an action item (not drops)."""
    reasons = ", ".join(f"{reason} {n}" for reason, n in sorted(row.reasons.items()))
    lines = [f"  dropped: {reasons or 'none'}"]
    for drop in row.drops:
        lines.append(f"    - [{drop.reason}] {drop.text}")
        lines += [f"        {line}" for line in drop.cited]
    lines.append(f"  decisions that repeated an action item: {row.tasks_as_decisions}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    safe_console()
    parser = argparse.ArgumentParser(description="Compare Ollama models on note writing")
    parser.add_argument("models", nargs="+")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--think", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--meeting-id", default=None, help="a stored meeting instead of fixtures")
    parser.add_argument("--show", action="store_true", help="print each note (console only)")
    parser.add_argument("--path", choices=PATHS, default="auto", help="one pass, or in parts")
    parser.add_argument("--minutes", default="", help="cuts of the 60-minute call: 15,30,45,60")
    args = parser.parse_args(argv)
    if args.meeting_id:
        cases = [meeting_case(args.meeting_id)]
    elif args.minutes:
        cases = cut_cases(load_case(FIXTURES / LONG_FIXTURE), args.minutes)
    else:
        cases = [load_case(p) for p in sorted(FIXTURES.glob("*.json"))]
    settings = path_settings(LlmSettings(think=args.think, keep_alive="5m"), args.path)
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
                    f"{model} {case.name}: {row.error or 'ok'} in {row.total_seconds:.1f} s",
                    flush=True,
                )
                if not row.error:
                    for line in format_drops(row):
                        print(line)
        with contextlib.suppress(LlmError):  # unload: one model in VRAM at a time
            provider.unload(model)
    print()
    for line in format_table(rows):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
