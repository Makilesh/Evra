"""Each line the owner typed during a call, linked to the transcript lines it was written about
(BUILD.md §7.2). A line typed at T looks at the utterances that ended from 90 s before T to 30 s
after it, and scores each by when it ended (best about 15 s before T), by the words they share
(BM25 over those candidates, scaled to the best) and, with an embedder, by meaning (the line as
a query, Qwen3's instruction format). The best five at or above MIN_SCORE are kept.

Every line's candidates go in one embedding batch, the job's only one before its chats (RB35): the
same embedder then checks the note, and its cache already holds these transcript lines. When
embedding fails, the time and the words decide, reweighted to fill the scale. Nothing here logs
note or transcript text."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import structlog

from evra.llm.provider import LlmError
from evra.notes.bm25 import Bm25, tokenize
from evra.notes.semantic import Embedder, as_query, cosine
from evra.store.meetings import Utterance
from evra.store.notepad import NoteLine

log = structlog.get_logger(__name__)

W_TIME, W_LEX, W_SEM, MIN_SCORE, MAX_PER_LINE = 0.4, 0.3, 0.3, 0.35, 5
BEFORE_S, AFTER_S, PEAK_S, SPREAD_S = 90, 30, 15, 30
ALIGN_TASK = (
    "Given a note typed during a meeting, retrieve the transcript lines it was written about"
)


@dataclass(frozen=True)
class Candidate:
    utterance_id: str
    w_time: float
    w_lex: float
    w_sem: float | None  # None: no meaning (no embedder, or the embedding failed)

    @property
    def score(self) -> float:
        if self.w_sem is None:
            return (W_TIME * self.w_time + W_LEX * self.w_lex) / (W_TIME + W_LEX)
        return W_TIME * self.w_time + W_LEX * self.w_lex + W_SEM * self.w_sem


def linkable(lines: Sequence[NoteLine]) -> list[NoteLine]:
    """The lines typed during the call (with a time), not pasted context."""
    return [
        line
        for line in lines
        if line.phase == "during" and not line.is_context and line.captured_at_ms is not None
    ]


def _near(at_ms: int, ordered: Sequence[Utterance], ends: Sequence[int]) -> list[Utterance]:
    """The utterances that end from BEFORE_S before `at_ms` to AFTER_S after it, by their end."""
    first = bisect_left(ends, at_ms - BEFORE_S * 1000)
    return list(ordered[first : bisect_right(ends, at_ms + AFTER_S * 1000)])


def _w_time(at_ms: int, utterance: Utterance) -> float:
    dt = (at_ms - utterance.end_ms) / 1000  # positive when typed after hearing it
    return math.exp(-(((dt - PEAK_S) / SPREAD_S) ** 2))


def _meanings(
    near: Mapping[str, tuple[NoteLine, list[Utterance]]], embedder: Embedder | None
) -> dict[str, dict[str, float]] | None:
    """For each line, max(0, cosine) with each candidate, in one batch; None when there is no
    embedder or the batch fails."""
    if embedder is None or not near:
        return None
    queries = [as_query(line.text, ALIGN_TASK) for line, _ in near.values()]
    texts = list(dict.fromkeys(u.text for _, found in near.values() for u in found))
    try:
        vectors = embedder.vectors([*queries, *texts])
    except LlmError as exc:  # linking still works, by time and words
        log.info("semantic_check_skipped", error=type(exc).__name__)
        return None
    by_text = dict(zip(texts, vectors[len(queries) :], strict=True))
    return {
        line.id: {u.id: max(0.0, cosine(query, by_text[u.text])) for u in found}
        for (line, found), query in zip(near.values(), vectors[: len(queries)], strict=True)
    }


def candidates(
    lines: Sequence[NoteLine], utterances: Sequence[Utterance], *, embedder: Embedder | None = None
) -> dict[str, list[Candidate]]:
    """Every linkable line's candidates, in the call's order, with the parts of their score."""
    ordered = sorted(utterances, key=lambda u: (u.end_ms, u.start_ms, u.seq))
    ends = [u.end_ms for u in ordered]
    near: dict[str, tuple[NoteLine, list[Utterance]]] = {}
    for line in linkable(lines):
        assert line.captured_at_ms is not None
        found = sorted(_near(line.captured_at_ms, ordered, ends), key=lambda u: (u.start_ms, u.seq))
        near[line.id] = (line, found)
    meaning = _meanings({k: v for k, v in near.items() if v[1]}, embedder)
    result: dict[str, list[Candidate]] = {}
    for line_id, (line, found) in near.items():
        assert line.captured_at_ms is not None
        words = Bm25([tokenize(u.text) for u in found]).scores(tokenize(line.text))
        top = max(words, default=0.0)
        result[line_id] = [
            Candidate(
                u.id,
                _w_time(line.captured_at_ms, u),
                score / top if top > 0 else 0.0,
                None if meaning is None else meaning[line_id][u.id],
            )
            for u, score in zip(found, words, strict=True)
        ]
    return result


def best(
    found: Sequence[Candidate], *, min_score: float = MIN_SCORE, most: int = MAX_PER_LINE
) -> list[tuple[str, float]]:
    """The candidates at or above `min_score`, best first (earlier first on a tie), at most
    `most` of them."""
    kept = sorted((c for c in found if c.score >= min_score), key=lambda c: -c.score)
    return [(c.utterance_id, c.score) for c in kept[:most]]


def align(
    lines: Sequence[NoteLine], utterances: Sequence[Utterance], *, embedder: Embedder | None = None
) -> dict[str, list[tuple[str, float]]]:
    """Each linkable line's id -> its kept (utterance id, score), best first; a line with
    nothing near it gets an empty list. Before, after and context lines are not linked."""
    found = candidates(lines, utterances, embedder=embedder)
    return {line_id: best(line_candidates) for line_id, line_candidates in found.items()}
