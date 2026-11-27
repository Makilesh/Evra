"""Asking one meeting one question: the meeting context (the same system message the note uses,
so Ollama reuses its cache), a question, the last few turns, then every point is checked against
the transcript before it is kept (by its words, and with an embedder by its meaning too). A call
too long to read whole sends the parts that best match the question. Nothing here logs or raises
with question, reply or transcript text."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import structlog

from evra.config import LlmSettings
from evra.llm.prompt_files import load_part
from evra.llm.provider import ChatMessage, ChatResult, LlmError, LlmProvider
from evra.llm.schemas import MeetingAnswer
from evra.notes.bm25 import Bm25, tokenize
from evra.notes.context import NONE, MeetingContext, as_data, estimate_tokens
from evra.notes.errors import NoteTooLong, NoTranscript
from evra.notes.semantic import Embedder, SemanticCheck, as_query, cosine
from evra.notes.structured import chat_structured
from evra.notes.user_notes import NO_NOTES, NotesInput, notes_context
from evra.notes.validate import KEPT_BY_MEANING, CheckedBullet, Grounder
from evra.store.meetings import Utterance

log = structlog.get_logger(__name__)

MAX_QUESTION_CHARS = 500
HISTORY_TURNS = 3
WINDOW_LINES, WINDOW_STRIDE = 6, 3
EXCERPT_TOKENS = 8000
LINE_OVERHEAD_TOKENS = 10  # the printed "[u:N] [mm:ss] Speaker: " before each line
ASK_TASK = "Given a question about a meeting, retrieve the transcript lines that answer it"
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


def output_tokens(settings: LlmSettings) -> int:
    """The reply room a question reserves: short, unless thinking needs the note's room."""
    return settings.max_output_tokens if settings.think else settings.ask_output_tokens


def ask_settings(llm: LlmSettings) -> LlmSettings:
    """Questions keep the model warm for a while, need only a short reply (more when the model
    thinks) and give up sooner than a note does."""
    return llm.model_copy(
        update={
            "keep_alive": llm.ask_keep_alive,
            "max_output_tokens": output_tokens(llm),
            "timeout_s": min(llm.timeout_s, llm.ask_timeout_s),
        }
    )


def clean_question(text: str) -> str | None:
    cleaned = " ".join(text.split())
    if not cleaned or len(cleaned) > MAX_QUESTION_CHARS:
        return None
    return cleaned


def whole_meeting_fits(context: MeetingContext, user_tokens: int, settings: LlmSettings) -> bool:
    limit = min(settings.context_budget, settings.num_ctx - output_tokens(settings))
    return context.estimated_tokens + user_tokens <= limit


def _windows(utterances: Sequence[Utterance]) -> list[Sequence[Utterance]]:
    """WINDOW_LINES lines every WINDOW_STRIDE, in time order."""
    ordered = sorted(utterances, key=lambda u: (u.start_ms, u.seq))
    return [ordered[i : i + WINDOW_LINES] for i in range(0, len(ordered), WINDOW_STRIDE)]


def _window_text(window: Sequence[Utterance]) -> str:
    return " ".join(u.text for u in window)


def window_texts(utterances: Sequence[Utterance]) -> list[str]:
    """The text of every window `excerpt_ids` ranks, in order: what a long call embeds."""
    return [_window_text(w) for w in _windows(utterances)]


def embed_parts(embedder: Embedder, utterances: Sequence[Utterance]) -> None:
    """Embed a long call's windows ahead of its questions (the Ask tab's pre-read), so each
    question on that embedder sends only its query. A failure is logged; the questions then
    embed what they need themselves, or go by words."""
    try:
        embedder.vectors(window_texts(utterances))
    except LlmError as exc:
        log.info("semantic_check_skipped", error=type(exc).__name__)


def excerpt_ids(
    utterances: Sequence[Utterance],
    question: str,
    budget_tokens: int = EXCERPT_TOKENS,
    *,
    embedder: Embedder | None = None,
) -> set[str]:
    """The lines of the windows that best match the question, best window first, while their
    printed size stays within the budget. A window scores by its words (BM25); with an
    embedder, half by its words (scaled to the best window's) and half by its meaning, so a
    question that shares no word with its answer ("What did I promise?") still finds it."""
    windows = _windows(utterances)
    texts = [_window_text(w) for w in windows]
    scores = Bm25([tokenize(t) for t in texts]).scores(tokenize(question))
    if embedder is not None:
        scores = _with_meaning(scores, texts, question, embedder)
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


def _with_meaning(
    scores: Sequence[float], texts: Sequence[str], question: str, embedder: Embedder
) -> list[float]:
    """0.5 * BM25 / best BM25 + 0.5 * max(0, cosine of the question and the window); the
    BM25 scores alone when embedding fails."""
    try:
        query, *windows = embedder.vectors([as_query(question, ASK_TASK), *texts])
    except LlmError as exc:  # asking still works, by words alone
        log.info("semantic_check_skipped", error=type(exc).__name__)
        return list(scores)
    best = max(scores, default=0.0)
    return [
        0.5 * (score / best if best else 0.0) + 0.5 * max(0.0, cosine(query, window))
        for score, window in zip(scores, windows, strict=True)
    ]


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


def _trimmed(recent: Sequence[Exchange]) -> list[Sequence[Exchange]]:
    """The history, then without its oldest exchange, and so on down to none."""
    return [recent[i:] for i in range(len(recent) + 1)]


@dataclass(frozen=True)
class _Prompt:
    context: MeetingContext
    messages: list[ChatMessage]
    version: str


def _parts_prompt(
    question: str,
    recent: Sequence[Exchange],
    *,
    meeting: Mapping[str, Any],
    utterances: Sequence[Utterance],
    gaps: Sequence[Mapping[str, Any]],
    notes: NotesInput,
    settings: LlmSettings,
    embedder: Embedder | None,
) -> _Prompt | None:
    """The prompt with only the parts of the call that best match the question (and all of the
    owner's notes). While it does not fit, the oldest exchanges go first; NoteTooLong when even
    none leaves no room, None when no part matches the question."""
    limit = min(settings.context_budget, settings.num_ctx - output_tokens(settings))

    def context_of(only: set[str]) -> MeetingContext:
        return notes_context(
            meeting=meeting, utterances=utterances, notes=notes, gaps=gaps, only=only
        )

    skeleton = context_of(set())
    # a follow-up ("When is it due?") is found through the question before it
    query = f"{question} {recent[-1].question}" if recent else question
    needed = 0
    for turns in _trimmed(recent):
        user_tokens = estimate_tokens(build_ask_messages(skeleton, question, turns)[0][1].content)
        needed = skeleton.estimated_tokens + user_tokens
        if needed > limit:
            continue
        budget = min(EXCERPT_TOKENS, limit - needed)
        chosen = excerpt_ids(utterances, query, budget, embedder=embedder)
        if not chosen:
            return None
        part = context_of(chosen)
        needed = part.estimated_tokens + user_tokens
        if whole_meeting_fits(part, user_tokens, settings):
            return _Prompt(part, *build_ask_messages(part, question, turns))
    raise NoteTooLong(needed, limit)


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
    notes: NotesInput = NO_NOTES,
    context: MeetingContext | None = None,
    embedder: Embedder | None = None,
) -> AskResult:
    """Asked on the meeting's shared context with the owner's `notes`: `context` when the caller
    built it (`meeting_context`), otherwise built here the same way. With an embedder, a long
    call's parts are chosen by meaning as well as words, and the answer's points are checked by
    meaning too. That check's one batch runs after the answer; choosing the parts needs its
    batch before it."""
    if not utterances:
        raise NoTranscript("no transcript")
    if context is None:
        context = notes_context(meeting=meeting, utterances=utterances, notes=notes, gaps=gaps)
    # Whole versus parts is decided on the meeting alone: when the history is what tips it over,
    # the oldest exchanges go first.
    recent = list(history)[-HISTORY_TURNS:]
    room = settings.num_ctx - output_tokens(settings)
    prompt: _Prompt | None = None
    for turns in _trimmed(recent):
        messages, version = build_ask_messages(context, question, turns)
        if whole_meeting_fits(context, estimate_tokens(messages[1].content), settings):
            prompt = _Prompt(context, messages, version)
            break
    if prompt is None:
        prompt = _parts_prompt(
            question,
            recent,
            meeting=meeting,
            utterances=utterances,
            gaps=gaps,
            notes=notes,
            settings=settings,
            embedder=embedder,
        )
    if prompt is None:
        log.info("question_answered", state="not_found", kept=0, dropped=0, excerpt=True)
        return AskResult(
            state="not_found",
            points=(),
            excerpt=True,
            model=model,
            prompt_version=build_ask_messages(context, question, ())[1],
            tokens_in=0,
            tokens_out=0,
            seconds=0.0,
            dropped=0,
        )
    context, version = prompt.context, prompt.version

    def too_long(first: ChatResult) -> None:
        if first.tokens_in >= room:  # Ollama cut the prompt to fit its context window
            raise NoteTooLong(first.tokens_in, room)

    reply = chat_structured(
        provider,
        model,
        prompt.messages,
        MeetingAnswer,
        max_output_tokens=output_tokens(settings),
        invalid_event="question_json_invalid",
        after_first=too_long,
    )
    if reply.repair_version:
        version = f"{version}+{reply.repair_version}"
    answer = reply.value

    kept: list[CheckedBullet] = []
    dropped = rescued = 0
    state: AnswerState = "not_found"
    if answer.found and answer.points:
        grounder = Grounder(
            aliases=context.aliases,
            utterance_text=context.utterance_text,
            user_notes=notes.user_notes,
            semantic=None if embedder is None else SemanticCheck(embedder),
        )
        for checked, how in grounder.check_all(answer.points):
            if checked is None:
                dropped += 1
                continue
            kept.append(checked)
            if how == KEPT_BY_MEANING:
                rescued += 1
        state = "answered" if kept else "unchecked"
    log.info(
        "question_answered",
        state=state,
        kept=len(kept),
        dropped=dropped,
        rescued=rescued,
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
