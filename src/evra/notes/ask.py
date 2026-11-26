"""Asking one meeting one question: the meeting context (the same system message the note uses,
so Ollama reuses its cache), a question, the last few turns, then every point is checked against
the transcript before it is kept. Nothing here logs or raises with question, reply or transcript
text."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from pydantic import ValidationError

from evra.config import LlmSettings
from evra.llm.prompt_files import load_part, load_prompt
from evra.llm.provider import ChatMessage, ChatResult, LlmProvider
from evra.llm.schemas import MeetingAnswer
from evra.notes.bm25 import Bm25, tokenize
from evra.notes.context import NONE, MeetingContext, as_data, build_context, estimate_tokens
from evra.notes.validate import CheckedBullet, Grounder
from evra.notes.writer import NoteCutOff, NoteInvalid, NoTranscript, strip_fences
from evra.store.meetings import Utterance

log = structlog.get_logger(__name__)

MAX_QUESTION_CHARS = 500
HISTORY_TURNS = 3
WINDOW_LINES, WINDOW_STRIDE = 6, 3
EXCERPT_TOKENS = 8000
NOT_DISCUSSED = "Not discussed in this meeting."
AnswerState = Literal["answered", "not_found", "unchecked"]


@dataclass(frozen=True)
class Exchange:
    question: str
    points: tuple[str, ...]  # empty = not discussed


@dataclass(frozen=True)
class AskResult:
    state: AnswerState
    points: tuple[CheckedBullet, ...]
    excerpt: bool
    model: str
    prompt_version: str
    tokens_in: int
    tokens_out: int
    cached_tokens: int
    seconds: float
    dropped: int


def ask_settings(llm: LlmSettings) -> LlmSettings:
    """Questions keep the model warm for a while and need only a short reply."""
    return llm.model_copy(
        update={"keep_alive": llm.ask_keep_alive, "max_output_tokens": llm.ask_output_tokens}
    )


def clean_question(text: str) -> str | None:
    cleaned = " ".join(text.split())
    if not cleaned or len(cleaned) > MAX_QUESTION_CHARS:
        return None
    return cleaned


def whole_meeting_fits(context: MeetingContext, user_tokens: int, settings: LlmSettings) -> bool:
    limit = min(settings.context_budget, settings.num_ctx - settings.ask_output_tokens)
    return context.estimated_tokens + user_tokens <= limit


def excerpt_ids(
    utterances: Sequence[Utterance], question: str, budget_tokens: int = EXCERPT_TOKENS
) -> set[str]:
    """The lines of the windows that best match the question, best window first, within budget."""
    ordered = sorted(utterances, key=lambda u: (u.start_ms, u.seq))
    starts = range(0, len(ordered), WINDOW_STRIDE)
    windows = [ordered[i : i + WINDOW_LINES] for i in starts]
    scores = Bm25([tokenize(" ".join(u.text for u in w)) for w in windows]).scores(
        tokenize(question)
    )
    ranked = sorted((i for i, s in enumerate(scores) if s > 0), key=lambda i: (-scores[i], i))
    chosen: set[str] = set()
    used = 0
    for i in ranked:
        fresh = [u for u in windows[i] if u.id not in chosen]
        cost = sum(estimate_tokens(u.text) for u in fresh)
        if used + cost > budget_tokens:
            continue
        chosen.update(u.id for u in fresh)
        used += cost
    return chosen


def _conversation(history: Sequence[Exchange]) -> str:
    turns = []
    for exchange in history[-HISTORY_TURNS:]:
        answer = " ".join(exchange.points) if exchange.points else NOT_DISCUSSED
        turns.append(f"Q: {as_data(exchange.question)}\nA: {as_data(answer)}")
    return "\n\n".join(turns) or NONE


def build_ask_messages(
    context: MeetingContext, question: str, history: Sequence[Exchange]
) -> tuple[list[ChatMessage], str]:
    task = load_part("a12_ask")
    user = task.render(
        conversation=_conversation(history),
        question=as_data(question),
        schema=json.dumps(MeetingAnswer.model_json_schema(), separators=(",", ":")),
    )
    messages = [ChatMessage("system", context.system), ChatMessage("user", user)]
    return messages, f"{context.version}+{task.version}"


def _parse(content: str) -> tuple[MeetingAnswer | None, str]:
    try:
        return MeetingAnswer.model_validate_json(strip_fences(content)), ""
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(p) for p in e['loc']) or 'document'}: {e['msg']}"
            for e in exc.errors(include_input=False, include_url=False)
        ]
        return None, "; ".join(problems)[:2000]


def ask_meeting(
    provider: LlmProvider,
    *,
    model: str,
    meeting: Mapping[str, Any],
    utterances: Sequence[Utterance],
    question: str,
    settings: LlmSettings,
    history: Sequence[Exchange] = (),
    gaps: Sequence[Mapping[str, Any]] = (),
    user_notes: str = NONE,
) -> AskResult:
    if not utterances:
        raise NoTranscript("no transcript")
    context = build_context(
        meeting=meeting, utterances=utterances, gaps=gaps, user_notes=user_notes
    )
    messages, version = build_ask_messages(context, question, history)
    if not whole_meeting_fits(context, estimate_tokens(messages[1].content), settings):
        context = build_context(
            meeting=meeting,
            utterances=utterances,
            gaps=gaps,
            user_notes=user_notes,
            only=excerpt_ids(utterances, question),
        )
        messages, version = build_ask_messages(context, question, history)
    schema = MeetingAnswer.model_json_schema()

    def call(chat: list[ChatMessage]) -> ChatResult:
        result = provider.chat_json(model, chat, schema)
        if result.truncated:
            raise NoteCutOff(settings.ask_output_tokens)
        return result

    calls = [call(messages)]
    answer, error = _parse(calls[0].content)
    if answer is None:
        repair = load_prompt("a9_repair")
        system, user = repair.render(
            schema=json.dumps(schema, separators=(",", ":")),
            error=error,
            bad_output=calls[0].content,
        )
        calls.append(call([ChatMessage("system", system), ChatMessage("user", user)]))
        version = f"{version}+{repair.version}"
        answer, error = _parse(calls[1].content)
        if answer is None:
            log.warning("question_json_invalid", model=model, error=error)
            raise NoteInvalid(model)

    kept: list[CheckedBullet] = []
    dropped = 0
    state: AnswerState = "not_found"
    if answer.found and answer.points:
        grounder = Grounder(
            aliases=context.aliases,
            utterance_text=context.utterance_text,
            user_notes="" if user_notes == NONE else user_notes,
        )
        for point in answer.points:
            checked, _ = grounder.check(point)
            if checked is None:
                dropped += 1
            else:
                kept.append(checked)
        state = "answered" if kept else "unchecked"
    seconds = sum(c.seconds for c in calls)
    log.info(
        "question_answered",
        state=state,
        kept=len(kept),
        dropped=dropped,
        excerpt=context.excerpt,
        seconds=round(seconds, 1),
        cached_tokens=sum(c.cached_tokens for c in calls),
    )
    return AskResult(
        state=state,
        points=tuple(kept),
        excerpt=context.excerpt,
        model=model,
        prompt_version=version,
        tokens_in=sum(c.tokens_in for c in calls),
        tokens_out=sum(c.tokens_out for c in calls),
        cached_tokens=sum(c.cached_tokens for c in calls),
        seconds=seconds,
        dropped=dropped,
    )
