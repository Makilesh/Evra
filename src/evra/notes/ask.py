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

from evra.config import LlmSettings
from evra.llm.prompt_files import load_part
from evra.llm.provider import ChatMessage, LlmProvider
from evra.llm.schemas import MeetingAnswer
from evra.notes.bm25 import Bm25, tokenize
from evra.notes.context import NONE, MeetingContext, as_data, build_context, estimate_tokens
from evra.notes.errors import NoteTooLong, NoTranscript
from evra.notes.structured import chat_structured
from evra.notes.validate import CheckedBullet, Grounder
from evra.store.meetings import Utterance

log = structlog.get_logger(__name__)

MAX_QUESTION_CHARS = 500
HISTORY_TURNS = 3
WINDOW_LINES, WINDOW_STRIDE = 6, 3
EXCERPT_TOKENS = 8000
LINE_OVERHEAD_TOKENS = 10  # the printed "[u:N] [mm:ss] Speaker: " before each line
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
    seconds: float
    dropped: int
    cached_tokens: int = 0


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
    """The lines of the windows that best match the question, best window first, while their
    printed size stays within the budget."""
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
        cost = sum(estimate_tokens(u.text) + LINE_OVERHEAD_TOKENS for u in fresh)
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
    user_tokens = estimate_tokens(messages[1].content)
    if not whole_meeting_fits(context, user_tokens, settings):
        limit = min(settings.context_budget, settings.num_ctx - settings.ask_output_tokens)
        skeleton = build_context(
            meeting=meeting, utterances=utterances, gaps=gaps, user_notes=user_notes, only=set()
        ).estimated_tokens
        # a follow-up ("When is it due?") is found through the question before it
        query = f"{question} {history[-1].question}" if history else question
        context = build_context(
            meeting=meeting,
            utterances=utterances,
            gaps=gaps,
            user_notes=user_notes,
            only=excerpt_ids(
                utterances, query, min(EXCERPT_TOKENS, limit - user_tokens - skeleton)
            ),
        )
        if not whole_meeting_fits(context, user_tokens, settings):
            raise NoteTooLong(context.estimated_tokens + user_tokens, limit)
        messages, version = build_ask_messages(context, question, history)
    reply = chat_structured(
        provider,
        model,
        messages,
        MeetingAnswer,
        max_output_tokens=settings.ask_output_tokens,
        invalid_event="question_json_invalid",
    )
    if reply.repair_version:
        version = f"{version}+{reply.repair_version}"
    answer = reply.value

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
    log.info(
        "question_answered",
        state=state,
        kept=len(kept),
        dropped=dropped,
        excerpt=context.excerpt,
        seconds=round(reply.seconds, 1),
        cached_tokens=reply.cached_tokens,
    )
    return AskResult(
        state=state,
        points=tuple(kept),
        excerpt=context.excerpt,
        model=model,
        prompt_version=version,
        tokens_in=reply.tokens_in,
        tokens_out=reply.tokens_out,
        seconds=reply.seconds,
        dropped=dropped,
        cached_tokens=reply.cached_tokens,
    )
