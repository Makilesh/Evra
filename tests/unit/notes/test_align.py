"""Aligning typed note lines to the transcript lines they were written about (BUILD.md §7.2)."""

import math
from collections.abc import Sequence

import pytest
import structlog

from evra.llm.provider import LlmModelMissing
from evra.notes.align import ALIGN_TASK, MAX_PER_LINE, MIN_SCORE, align
from evra.notes.semantic import Embedder, as_query
from evra.store.meetings import Utterance
from evra.store.notepad import NoteLine, Phase
from tests.unit.notes.fakes import FakeProvider, utt

T = 600_000  # the note is typed 10 minutes into the call


def note(
    line_id: str,
    text: str,
    at_ms: int | None = T,
    *,
    phase: Phase = "during",
    is_context: bool = False,
) -> NoteLine:
    return NoteLine(line_id, 0, text, at_ms, phase, is_context, ())


def ending(uid: str, seconds_before: float, text: str, seq: int = 0) -> Utterance:
    """A line that ended `seconds_before` the note was typed (negative: after it)."""
    end = T - round(seconds_before * 1000)
    return utt(uid, 1, end - 3_000, end, text, seq=seq)


def w_time(dt: float) -> float:
    return math.exp(-(((dt - 15) / 30) ** 2))


def _basis(i: int, dims: int = 16) -> list[float]:
    return [1.0 if k == i else 0.0 for k in range(dims)]


class Meanings(FakeProvider):
    """Texts named together embed to the same vector, so their cosine is 1; every other text
    embeds to one vector of its own, at a right angle to them (cosine 0)."""

    def __init__(self, *alike: tuple[str, ...]) -> None:
        super().__init__([])
        self.alike = alike

    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        self.embed_calls.append(list(texts))
        groups = [next((g for g, alike in enumerate(self.alike) if t in alike), 15) for t in texts]
        return [_basis(g) for g in groups]


class NoEmbeddings(FakeProvider):
    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        raise LlmModelMissing(model)


def test_align_prefers_the_line_heard_just_before() -> None:
    said = "The Atlas beta moves to March 3."
    lines = [
        ending("long_ago", 90.5, said, 0),  # ended more than 90 s before: not a candidate
        ending("earlier", 70, said, 1),
        ending("just_before", 15, said, 2),
        ending("after", -25, said, 3),
        ending("too_late", -30.5, said, 4),  # ended more than 30 s after: not a candidate
    ]
    aligned = align([note("n1", "Atlas beta: March 3")], lines)
    assert [uid for uid, _ in aligned["n1"]] == ["just_before", "after", "earlier"]
    assert aligned["n1"][0][1] == pytest.approx(1.0)  # its words, at the peak 15 s after


def test_candidates_end_from_90_s_before_to_30_s_after() -> None:
    said = "The Atlas beta moves to March 3."
    lines = [ending("first", 90, said, 0), ending("last", -30, said, 1)]
    assert {uid for uid, _ in align([note("n1", "Atlas beta")], lines)["n1"]} == {"first", "last"}


def test_align_uses_words_and_meaning() -> None:
    typed = "budget signed off"
    lines = [
        ending("words", 50, "The budget is in.", 0),
        ending("meaning", 50, "Finance approved the money yesterday.", 1),
        ending("neither", 50, "Nice weather today.", 2),
    ]
    query = as_query(typed, ALIGN_TASK)
    provider = Meanings((query, "Finance approved the money yesterday."))
    aligned = align([note("n1", typed)], lines, embedder=Embedder(provider, "embed"))
    by_time = 0.4 * w_time(50)  # 0.10, under MIN_SCORE: "neither" is left out
    assert by_time < MIN_SCORE
    assert dict(aligned["n1"]) == pytest.approx({"words": by_time + 0.3, "meaning": by_time + 0.3})
    [batch] = provider.embed_calls  # one batch: the note as a query, then its candidates
    assert batch[0] == query
    assert sorted(batch[1:]) == sorted(u.text for u in lines)


def test_align_without_embeddings_reweights() -> None:
    lines = [
        ending("words", 50, "The budget is in.", 0),
        ending("meaning", 50, "Finance approved the money yesterday.", 1),
    ]
    typed = [note("n1", "budget signed off")]
    aligned = align(typed, lines)
    # (0.4 w_time + 0.3 w_lex) / 0.7: the words keep their line, time alone does not
    assert dict(aligned["n1"]) == pytest.approx({"words": (0.4 * w_time(50) + 0.3) / 0.7})
    with structlog.testing.capture_logs() as logs:
        failed = align(typed, lines, embedder=Embedder(NoEmbeddings([]), "embed"))
    assert failed == aligned  # a failed embedding falls back to the same weights (RB35)
    skipped = [e for e in logs if e["event"] == "semantic_check_skipped"]
    assert skipped == [
        {"event": "semantic_check_skipped", "error": "LlmModelMissing", "log_level": "info"}
    ]


def test_context_lines_are_not_aligned() -> None:
    lines = [ending("u1", 15, "The budget is in.")]
    notes = [
        note("pasted", "The budget is in. " * 40, is_context=True),
        note("early", "budget", -60_000, phase="before"),
        note("late", "budget", T + 5_000, phase="after"),
        note("untimed", "budget", None),
    ]
    provider = FakeProvider([])
    assert align(notes, lines, embedder=Embedder(provider, "embed")) == {}
    assert provider.embed_calls == []  # nothing to link: no embedding request
    typed = note("typed", "budget")
    assert set(align([*notes, typed], lines)) == {"typed"}


def test_at_most_five_lines_per_note_best_first() -> None:
    lines = [ending(f"u{k}", 5 + 4 * k, "The budget is in.", k) for k in range(8)]
    kept = align([note("n1", "budget")], lines)["n1"]
    assert len(kept) == MAX_PER_LINE
    scores = [score for _, score in kept]
    assert scores == sorted(scores, reverse=True)
    assert all(score >= MIN_SCORE for score in scores)


def test_a_line_with_nothing_near_it_is_linked_to_nothing() -> None:
    lines = [ending("u1", 300, "The budget is in.")]
    assert align([note("n1", "budget")], lines) == {"n1": []}
