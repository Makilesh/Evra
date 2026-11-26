"""Asking bake-off (spec 2026-11-26 §8): the app's own asking code puts one question to the
60-minute synthetic 1:1 for each planted fact and one for each topic it never mentions.

    uv run python tools/bakeoff_ask.py gemma4:12b qwen3.5:9b
    uv run python tools/bakeoff_ask.py gemma4:12b --show     # every answer and its check

Per model: facts answered correctly (the model's answer holds every keyword of the fact, "a|b"
meaning either, and again after the transcript check), absent topics answered "not
discussed", answers the check lets through, the first question from a cold model, the first
question after the same model wrote the note (A1) and named the meeting (A8), the window's
order: seconds, Ollama's prompt token count
and how many of those tokens it reused from its cache, then the follow-ups (median and worst
seconds) and whether only parts of the call were read. Each question stands alone (no earlier
turns). Synthetic fixtures only (BUILD.md §9.3).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import statistics
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from evra.config import LlmSettings
from evra.console import safe_console
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import ChatMessage, ChatResult, LlmError, LlmProvider
from evra.llm.schemas import MeetingAnswer, MeetingTitle
from evra.notes.ask import ask_meeting, ask_settings
from evra.notes.context import MeetingContext, build_context
from evra.notes.errors import NoteError
from evra.notes.structured import parse_reply
from evra.notes.templates import load_template
from evra.notes.title import clean_generated_title, title_messages, title_settings
from evra.notes.validate import CheckedNote, Grounder
from evra.notes.writer import write_note

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # `tools` when run as a script

from tools.bakeoff_notes import FIXTURES, Case, load_case

Phase = Literal["cold", "warm", "after_note"]
DEFAULT_FIXTURE = "one_on_one_60min_synthetic"
_INLINE = re.compile(r"\s*\[[^\]]*\]")  # an inline citation mark such as " [u:12, u:13]"


@dataclass(frozen=True)
class Probe:
    question: str
    keywords: tuple[str, ...]  # every one in the answer, "a|b" = either; () = never discussed

    @property
    def absent(self) -> bool:
        return not self.keywords


def load_probes(path: Path) -> tuple[Probe, ...]:
    """The fixture's fact questions in order, then the topics the call never mentions."""
    data = json.loads(path.read_text(encoding="utf-8"))
    facts = [Probe(e["question"], tuple(e["keywords"])) for e in data["expected"]]
    return (*facts, *(Probe(question, ()) for question in data["absent"]))


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
    tokens_in: int  # Ollama's prompt_eval_count: the whole prompt
    cached_tokens: int  # of those, reused from Ollama's cache
    excerpt: bool
    error: str = ""

    @property
    def absent(self) -> bool:
        return not self.keywords

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


def summary(rows: Sequence[Row]) -> Summary:
    """One model's rows. The cold and warm questions are scored; the question asked again right
    after the note is a timing only. Failed questions count as wrong and are left out of the
    times."""
    scored = [r for r in rows if r.phase != "after_note"]
    facts = [r for r in scored if not r.absent]
    absent = [r for r in scored if r.absent]
    cold = next((r for r in scored if r.phase == "cold" and not r.error), None)
    warm = [r for r in scored if r.phase == "warm" and not r.error]
    seconds = [r.seconds for r in warm]
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
    provider: Recorder, model: str, case: Case, probe: Probe, settings: LlmSettings, phase: Phase
) -> Row:
    provider.replies.clear()
    try:
        result = ask_meeting(
            provider,
            model=model,
            meeting=case.meeting,
            utterances=case.utterances,
            question=probe.question,
            settings=settings,
        )
    except (LlmError, NoteError) as exc:
        return Row(
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
            error=type(exc).__name__,
        )
    # ask_meeting used the last reply: the first, or its repair when that was not valid JSON
    raw, _ = parse_reply(MeetingAnswer, provider.replies[-1])
    said = answer_text(p.text for p in raw.points) if raw is not None and raw.found else ""
    return Row(
        model=model,
        phase=phase,
        question=probe.question,
        keywords=probe.keywords,
        state=result.state,
        answer=said,
        shown=answer_text(p.text for p in result.points),
        kept=len(result.points),
        dropped=result.dropped,
        seconds=result.seconds,
        tokens_in=result.tokens_in,
        cached_tokens=result.cached_tokens,
        excerpt=result.excerpt,
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
    for point in raw.points:
        checked, reason = grounder.check(point)
        lines.append(
            f"      - {point.text} [{', '.join(point.citations)}]"
            f" -> {'kept' if checked is not None else 'dropped: ' + reason}"
        )
        if checked is None:
            for citation in point.citations:
                if citation in context.aliases:
                    said = context.utterance_text[context.aliases[citation]]
                    lines.append(f"          {citation}: {said}")
    return lines


def title_after_note(
    llm: LlmSettings, model: str, case: Case, note: CheckedNote
) -> tuple[str | None, float]:
    """The window's next step: the title call (A8) on the meeting's shared context, from the
    note just written. Returns the cleaned title and the seconds it took."""
    bullets = [b.text for b in note.summary] + [b.text for s in note.sections for b in s.bullets]
    text = "\n".join("- " + " ".join(b.split()) for b in bullets)
    context = build_context(meeting=case.meeting, utterances=case.utterances)
    messages, _ = title_messages(context, text)
    started = time.monotonic()
    reply = OllamaProvider(title_settings(llm)).chat_json(
        model, messages, MeetingTitle.model_json_schema()
    )
    seconds = time.monotonic() - started
    raw, _ = parse_reply(MeetingTitle, reply.content)
    return (None if raw is None else clean_generated_title(raw.title)), seconds


def _unload(provider: OllamaProvider, model: str) -> None:
    """Unload the model and wait until Ollama no longer lists it, so the next call is cold."""
    with contextlib.suppress(LlmError):
        provider.unload(model)
        for _ in range(60):
            if provider.gpu_share(model) is None:
                return
            time.sleep(0.25)


def run_model(
    model: str, case: Case, probes: Sequence[Probe], llm: LlmSettings, *, show: bool
) -> tuple[list[Row], float | None]:
    """The first question loads the model (cold), the rest follow it (warm). Then the same model
    writes the note with the app's note settings, names the meeting from it, and the first question
    is asked again at once, inside the note's keep-alive."""
    asking = ask_settings(llm)
    asker = Recorder(OllamaProvider(asking))
    noter = OllamaProvider(llm)
    context = build_context(meeting=case.meeting, utterances=case.utterances)
    grounder = Grounder(aliases=context.aliases, utterance_text=context.utterance_text)

    def asked(probe: Probe, phase: Phase, n: int) -> Row:
        row = ask_one(asker, model, case, probe, asking, phase)
        print(
            f"{model} {phase} {n}/{len(probes)}: {row.error or row.state} in {row.seconds:.1f} s,"
            f" {row.cached_tokens}/{row.tokens_in} prompt tokens reused · {probe.question}",
            flush=True,
        )
        if show:
            for line in _explain(asker, grounder, context):
                print(line)
        return row

    _unload(noter, model)
    rows = [asked(p, "cold" if i == 0 else "warm", i + 1) for i, p in enumerate(probes)]
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
        rows.append(asked(probes[0], "after_note", 1))
    _unload(noter, model)  # one model in VRAM at a time
    return rows, note_seconds


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def format_rows(rows: Sequence[Row]) -> list[str]:
    lines = [
        "| model | when | question | state | correct | correct as shown | kept/dropped"
        " | seconds | prompt tokens | reused |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r.model} | {r.phase} | {r.question} | {r.error or r.state} | {_yes(r.correct)}"
            f" | {_yes(r.shown_correct)} | {r.kept}/{r.dropped} | {r.seconds:.1f}"
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
        f"- first question, cold: {_seconds(s.cold_seconds)}",
    ]
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
    args = parser.parse_args(argv)
    path = FIXTURES / f"{args.fixture}.json"
    if not path.is_file():
        print(f"No fixture {path}", file=sys.stderr)
        return 2
    try:
        probes = load_probes(path)
    except KeyError:
        print(f"{path.name} has no questions (tools/make_long_fixture.py)", file=sys.stderr)
        return 2
    case = load_case(path)
    runs = [run_model(model, case, probes, LlmSettings(), show=args.show) for model in args.models]
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
