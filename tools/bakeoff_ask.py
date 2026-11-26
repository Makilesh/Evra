"""Asking bake-off (spec 2026-11-26 §8): the app's own asking code puts one question to the
60-minute synthetic 1:1 for each planted fact and one for each topic it never mentions.

    uv run python tools/bakeoff_ask.py gemma4:12b qwen3.5:9b
    uv run python tools/bakeoff_ask.py gemma4:12b --show     # every answer and its check
    uv run python tools/bakeoff_ask.py gemma4:12b --hours 2 --one-click --no-embed

Per model: facts answered correctly (the model's answer holds every keyword of the fact, "a|b"
meaning either, and again after the transcript check), absent topics answered "not discussed",
answers the check lets through, the first question from a cold model, the first question after
the same model wrote the note (A1) and named the meeting (A8), the window's order: seconds,
Ollama's prompt token count and how many of those tokens it reused, then the follow-ups (median
and worst seconds) and whether only parts of the call were read. Each question stands alone.
--hours 2 joins the call to itself an hour later (too long to read whole); --one-click adds the
Ask tab's four one-click questions, scored on whether they read any lines; --no-embed chooses
parts and checks points by words alone (the app also uses meaning). Synthetic fixtures only
(BUILD.md §9.3).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from evra.config import LlmSettings
from evra.console import safe_console
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import ChatMessage, ChatResult, LlmError, LlmProvider
from evra.llm.schemas import MeetingAnswer
from evra.notes.ask import ask_meeting, ask_settings
from evra.notes.context import MeetingContext, build_context
from evra.notes.errors import NoteError
from evra.notes.semantic import Embedder, SemanticCheck
from evra.notes.structured import parse_reply
from evra.notes.templates import load_template
from evra.notes.validate import Grounder
from evra.notes.writer import write_note

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # `tools` when run as a script

from tools.bakeoff_notes import FIXTURES, Case, load_case, repeat_case
from tools.bakeoff_steps import pre_read, title_after_note, unload

Phase = Literal["cold", "warm", "after_note", "after_prepare"]
DEFAULT_FIXTURE = "one_on_one_60min_synthetic"
_INLINE = re.compile(r"\s*\[[^\]]*\]")  # an inline citation mark such as " [u:12, u:13]"
ONE_CLICK = tuple(  # the Ask tab's one-click questions (frontend/src/strings.ts askSuggestions)
    ["What did I promise?", "What did they promise?", "What did we decide?", "What's still open?"]
)


@dataclass(frozen=True)
class Probe:
    question: str
    keywords: tuple[str, ...]  # every one in the answer, "a|b" = either; () = never discussed
    open: bool = False  # a one-click question: no one right answer, scored on reading lines

    @property
    def absent(self) -> bool:
        return not self.keywords and not self.open


def load_probes(path: Path, *, one_click: bool = False) -> tuple[Probe, ...]:
    """The fixture's fact questions in order, then the topics the call never mentions, then
    (when asked for) the one-click questions."""
    data = json.loads(path.read_text(encoding="utf-8"))
    facts = [Probe(e["question"], tuple(e["keywords"])) for e in data["expected"]]
    absent = [Probe(question, ()) for question in data["absent"]]
    opens = [Probe(question, (), open=True) for question in ONE_CLICK] if one_click else []
    return (*facts, *absent, *opens)


def correct(answer_text: str, keywords: Sequence[str]) -> bool:
    """The answer holds every keyword; "a|b" accepts either spelling."""
    text = answer_text.lower()
    return all(any(alt in text for alt in keyword.lower().split("|")) for keyword in keywords)


def answer_text(points: Iterable[str]) -> str:
    """Points as one text, without inline citation marks (their ids are digits)."""
    return " ".join(" ".join(_INLINE.sub("", point).split()) for point in points)


@dataclass(frozen=True)
class Row:
    model: str
    phase: Phase
    question: str
    keywords: tuple[str, ...]
    state: str  # answered | not_found | unchecked | failed
    answer: str  # the model's points before the check ("" when it found nothing)
    shown: str  # the points the check kept: what the owner sees
    kept: int
    dropped: int
    seconds: float
    tokens_in: int  # Ollama's prompt_eval_count: the whole prompt (0: the model was not asked)
    cached_tokens: int  # of those, reused from Ollama's cache
    excerpt: bool
    error: str = ""
    open: bool = False  # a one-click question
    total_seconds: float = 0.0  # the whole question: choosing parts, the answer, the check

    @property
    def absent(self) -> bool:
        return not self.keywords and not self.open

    @property
    def read_lines(self) -> bool:  # a long call with no matching part sends the model nothing
        return not self.error and self.tokens_in > 0

    @property
    def correct(self) -> bool:
        if self.absent:
            return self.state == "not_found"
        return not self.error and correct(self.answer, self.keywords)

    @property
    def shown_correct(self) -> bool:
        if self.absent:
            return self.state == "not_found"
        return self.state == "answered" and correct(self.shown, self.keywords)


@dataclass(frozen=True)
class Summary:
    model: str
    facts: int
    correct: int  # the model's answer holds the fact
    shown_correct: int  # and so do the points the check kept
    checked: int  # answers the check let through (at least one point kept)
    absent: int
    not_discussed: int
    kept: int
    dropped: int
    errors: int
    cold_seconds: float | None
    follow_ups: int
    follow_up_median: float | None
    follow_up_worst: float | None
    follow_up_reused: float | None  # median prompt tokens Ollama reused per follow-up
    after_note: Row | None
    excerpt: bool
    one_click: int = 0
    one_click_read: int = 0  # of those, how many sent the model any lines
    one_click_kept: int = 0  # points shown for them
    total_median: float | None = None  # per follow-up, choosing parts and the check included
    total_worst: float | None = None
    cold_total: float | None = None
    after_prepare: Row | None = None  # the first question again, after the Ask tab's pre-read


def summary(rows: Sequence[Row]) -> Summary:
    """One model's rows. The cold and warm questions are scored; the question asked again right
    after the note or after a pre-read is a timing only. Failed questions count as wrong and are
    left out of the times. One-click questions count only for whether they read any lines."""
    scored = [r for r in rows if r.phase in ("cold", "warm")]
    facts = [r for r in scored if not r.absent and not r.open]
    absent = [r for r in scored if r.absent]
    opens = [r for r in scored if r.open]
    cold = next((r for r in scored if r.phase == "cold" and not r.error), None)
    warm = [r for r in scored if r.phase == "warm" and not r.error]
    seconds = [r.seconds for r in warm]
    totals = [r.total_seconds for r in warm]
    return Summary(
        model=rows[0].model if rows else "",
        facts=len(facts),
        correct=sum(r.correct for r in facts),
        shown_correct=sum(r.shown_correct for r in facts),
        checked=sum(r.state == "answered" for r in facts),
        absent=len(absent),
        not_discussed=sum(r.state == "not_found" for r in absent),
        kept=sum(r.kept for r in facts),
        dropped=sum(r.dropped for r in facts),
        errors=sum(bool(r.error) for r in scored),
        cold_seconds=cold.seconds if cold else None,
        follow_ups=len(warm),
        follow_up_median=statistics.median(seconds) if seconds else None,
        follow_up_worst=max(seconds) if seconds else None,
        follow_up_reused=statistics.median(r.cached_tokens for r in warm) if warm else None,
        after_note=next((r for r in rows if r.phase == "after_note" and not r.error), None),
        excerpt=any(r.excerpt for r in scored),
        one_click=len(opens),
        one_click_read=sum(r.read_lines for r in opens),
        one_click_kept=sum(r.kept for r in opens),
        total_median=statistics.median(totals) if totals else None,
        total_worst=max(totals) if totals else None,
        cold_total=cold.total_seconds if cold else None,
        after_prepare=next((r for r in rows if r.phase == "after_prepare" and not r.error), None),
    )


class Recorder:
    """Passes calls on and keeps the replies, so the model's own answer can be scored before
    the transcript check drops anything."""

    def __init__(self, inner: LlmProvider) -> None:
        self.inner = inner
        self.name = inner.name
        self.replies: list[str] = []

    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        result = self.inner.chat_json(model, messages, schema)
        self.replies.append(result.content)
        return result

    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        return self.inner.embed(model, texts)

    def installed_models(self) -> list[str]:
        return self.inner.installed_models()

    def load(self, model: str) -> None:
        self.inner.load(model)


def ask_one(
    provider: Recorder,
    model: str,
    case: Case,
    probe: Probe,
    settings: LlmSettings,
    phase: Phase,
    *,
    embedder: Embedder | None = None,
) -> Row:
    """One question as the window asks it; with an embedder (the meeting's, kept across its
    questions as the window keeps it), by meaning too."""
    provider.replies.clear()
    failed = Row(
        model=model,
        phase=phase,
        question=probe.question,
        keywords=probe.keywords,
        state="failed",
        answer="",
        shown="",
        kept=0,
        dropped=0,
        seconds=0.0,
        tokens_in=0,
        cached_tokens=0,
        excerpt=False,
        open=probe.open,
    )
    started = time.monotonic()
    try:
        result = ask_meeting(
            provider,
            model=model,
            meeting=case.meeting,
            utterances=case.utterances,
            question=probe.question,
            settings=settings,
            embedder=embedder,
        )
    except (LlmError, NoteError) as exc:
        return replace(failed, error=type(exc).__name__)
    total = time.monotonic() - started
    # ask_meeting used the last reply: the first, or its repair when that was not valid JSON
    # (none when a long call had no part to read)
    raw = parse_reply(MeetingAnswer, provider.replies[-1])[0] if provider.replies else None
    return replace(
        failed,
        state=result.state,
        answer=answer_text(p.text for p in raw.points) if raw is not None and raw.found else "",
        shown=answer_text(p.text for p in result.points),
        kept=len(result.points),
        dropped=result.dropped,
        seconds=result.seconds,
        tokens_in=result.tokens_in,
        cached_tokens=result.cached_tokens,
        excerpt=result.excerpt,
        total_seconds=total,
    )


def _explain(provider: Recorder, grounder: Grounder, context: MeetingContext) -> list[str]:
    """Each point the model gave, its citations and what the check made of it; a dropped
    point's cited lines too."""
    raw, _ = parse_reply(MeetingAnswer, provider.replies[-1]) if provider.replies else (None, "")
    if raw is None:
        return ["      (no usable reply)"]
    if not raw.found:
        return ["      (not discussed)"]
    lines: list[str] = []
    for point, (checked, reason) in zip(raw.points, grounder.check_all(raw.points), strict=True):
        verdict = f"dropped: {reason}" if checked is None else f"kept {reason}".strip()
        lines.append(f"      - {point.text} [{', '.join(point.citations)}] -> {verdict}")
        if checked is None or reason:  # what a dropped point, or one kept by meaning, cites
            for citation in point.citations:
                if citation in context.aliases:
                    said = context.utterance_text[context.aliases[citation]]
                    lines.append(f"          {citation}: {said}")
    return lines


def run_model(
    model: str,
    case: Case,
    probes: Sequence[Probe],
    llm: LlmSettings,
    *,
    show: bool,
    embed: bool = True,
) -> tuple[list[Row], float | None]:
    """The first question loads the model (cold), the rest follow it (warm). Then the same model
    writes the note with the app's note settings, names the meeting from it, and the first question
    is asked again at once, inside the note's keep-alive. With `embed`, every question shares one
    embedder, as the window keeps one per meeting; a long call's first question is then asked
    once more after the Ask tab's pre-read (both models unloaded first)."""
    asking = ask_settings(llm)
    asker = Recorder(OllamaProvider(asking))
    noter = OllamaProvider(llm)
    context = build_context(meeting=case.meeting, utterances=case.utterances)
    meaning = SemanticCheck(Embedder(asker, llm.embedding_model)) if embed else None  # --show
    grounder = Grounder(
        aliases=context.aliases, utterance_text=context.utterance_text, semantic=meaning
    )
    cold = [model, llm.embedding_model] if embed else [model]

    def asked(probe: Probe, phase: Phase, n: int, embedder: Embedder | None) -> Row:
        row = ask_one(asker, model, case, probe, asking, phase, embedder=embedder)
        print(
            f"{model} {phase} {n}/{len(probes)}: {row.error or row.state} in {row.seconds:.1f} s"
            f" ({row.total_seconds:.1f} s in all), {row.cached_tokens}/{row.tokens_in} prompt"
            f" tokens reused | {probe.question}",
            flush=True,
        )
        if show:
            for line in _explain(asker, grounder, context):
                print(line)
        return row

    for name in cold:
        unload(noter, name)
    meeting = Embedder(asker, llm.embedding_model) if embed else None  # the window's, per meeting
    rows = [asked(p, "cold" if i == 0 else "warm", i + 1, meeting) for i, p in enumerate(probes)]
    note_seconds: float | None = None
    try:
        note = write_note(
            noter,
            model=model,
            meeting=case.meeting,
            utterances=case.utterances,
            template=load_template(str(case.meeting["template"])),
            settings=llm,
        )
        note_seconds = note.seconds
        print(f"{model} note: {note.note.kept} points in {note.seconds:.1f} s", flush=True)
        # the window names the meeting between the note and the first question
        try:
            title, title_seconds = title_after_note(llm, model, case, note.note)
            print(f"{model} title: {title!r} in {title_seconds:.1f} s", flush=True)
        except (LlmError, NoteError) as exc:
            print(f"{model} title: {type(exc).__name__}", flush=True)
    except (LlmError, NoteError) as exc:
        print(f"{model} note: {type(exc).__name__}", flush=True)
    if note_seconds is not None:
        rows.append(asked(probes[0], "after_note", 1, meeting))
    if embed and any(r.excerpt for r in rows):  # a long call: the first question after a pre-read
        for name in cold:
            unload(noter, name)
        prepared = Embedder(asker, llm.embedding_model)
        seconds = pre_read(asker, model, prepared, case.utterances)
        print(f"{model} pre-read: model loaded, parts embedded in {seconds:.1f} s", flush=True)
        rows.append(asked(probes[0], "after_prepare", 1, prepared))
    unload(noter, model)  # one model in VRAM at a time
    return rows, note_seconds


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def format_rows(rows: Sequence[Row]) -> list[str]:
    lines = [
        "| model | when | question | state | correct | correct as shown | kept/dropped"
        " | seconds | in all | prompt tokens | reused |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        scored = "-" if r.open else _yes(r.correct)
        shown = "-" if r.open else _yes(r.shown_correct)
        lines.append(
            f"| {r.model} | {r.phase} | {r.question} | {r.error or r.state} | {scored}"
            f" | {shown} | {r.kept}/{r.dropped} | {r.seconds:.1f} | {r.total_seconds:.1f}"
            f" | {r.tokens_in} | {r.cached_tokens} |"
        )
    return lines


def _seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f} s"


def format_summary(s: Summary, note_seconds: float | None) -> list[str]:
    lines = [
        f"## {s.model}",
        f"- facts correct: {s.correct}/{s.facts} (target >= {s.facts - 1});"
        f" still correct after the check: {s.shown_correct}/{s.facts}",
        f"- not discussed: {s.not_discussed}/{s.absent} (target {s.absent}/{s.absent})",
        f"- answers passing the check: {s.checked}/{s.facts} (target >= {s.facts - 2});"
        f" points kept {s.kept}, dropped {s.dropped}",
        f"- first question, cold: {_seconds(s.cold_seconds)} ({_seconds(s.cold_total)} in all)",
    ]
    if s.after_prepare is not None:
        lines.append(
            f"- first question after the Ask tab's pre-read: {s.after_prepare.seconds:.1f} s"
            f" ({s.after_prepare.total_seconds:.1f} s in all)"
        )
    after = s.after_note
    if after is None:
        lines.append("- first question right after the note: -")
    else:
        share = after.cached_tokens / after.tokens_in if after.tokens_in else 0.0
        lines.append(
            f"- first question after the note and title (note written in {_seconds(note_seconds)}):"
            f" {after.seconds:.1f} s; prompt {after.tokens_in} tokens, {after.cached_tokens}"
            f" reused ({share:.0%})"
        )
    reused = "-" if s.follow_up_reused is None else f"{s.follow_up_reused:.0f}"
    lines.append(
        f"- follow-ups ({s.follow_ups}): median {_seconds(s.follow_up_median)}, worst"
        f" {_seconds(s.follow_up_worst)} (target median <= 3 s); median {reused} prompt"
        " tokens reused"
    )
    lines.append(
        f"- follow-ups in all (choosing parts, the answer and its check): median"
        f" {_seconds(s.total_median)}, worst {_seconds(s.total_worst)}"
    )
    if s.one_click:
        lines.append(
            f"- one-click questions that read any lines: {s.one_click_read}/{s.one_click};"
            f" points shown {s.one_click_kept}"
        )
    lines.append(f"- excerpt mode: {_yes(s.excerpt)}")
    if s.errors:
        lines.append(f"- failed questions: {s.errors}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    safe_console()
    parser = argparse.ArgumentParser(description="Ask a synthetic call about its planted facts")
    parser.add_argument("models", nargs="+")
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE, help="in tests/fixtures/notes")
    parser.add_argument("--show", action="store_true", help="print every answer and its check")
    parser.add_argument("--hours", type=int, default=1, help="say the call N times, an hour apart")
    parser.add_argument("--one-click", action="store_true", help="add the one-click questions")
    parser.add_argument(
        "--embed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="choose parts and check points by meaning too (the app's way)",
    )
    args = parser.parse_args(argv)
    path = FIXTURES / f"{args.fixture}.json"
    if not path.is_file():
        print(f"No fixture {path}", file=sys.stderr)
        return 2
    try:
        probes = load_probes(path, one_click=args.one_click)
    except KeyError:
        print(f"{path.name} has no questions (tools/make_long_fixture.py)", file=sys.stderr)
        return 2
    case = repeat_case(load_case(path), args.hours)
    print(f"# {case.name}: {len(case.utterances)} lines, by meaning too: {_yes(args.embed)}")
    runs = [
        run_model(model, case, probes, LlmSettings(), show=args.show, embed=args.embed)
        for model in args.models
    ]
    print()
    for line in format_rows([row for rows, _ in runs for row in rows]):
        print(line)
    for rows, note_seconds in runs:
        print()
        for line in format_summary(summary(rows), note_seconds):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
