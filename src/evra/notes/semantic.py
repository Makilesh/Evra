"""Meaning-based checks with embeddings (BUILD.md D17, changed 2026-11-26: through Ollama).

Qwen3-Embedding wants an instruction on the query side only; documents carry none. Vectors
arrive at unit length, so the cosine is a dot product.
"""

from __future__ import annotations

from collections.abc import Sequence

from evra.llm.provider import LlmProvider

SUPPORT_COSINE = 0.55  # Task 2 may raise it from its calibration
QUERY_TASK = "Given a statement from meeting notes, retrieve the transcript lines that say it"


def as_query(text: str, task: str = QUERY_TASK) -> str:
    return f"Instruct: {task}\nQuery:{text}"


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class Embedder:
    """Embeds texts in batches; each distinct text is embedded once per instance."""

    def __init__(self, provider: LlmProvider, model: str, *, batch: int = 64) -> None:
        self._provider = provider
        self._model = model
        self._batch = batch
        self._cache: dict[str, list[float]] = {}

    def vectors(self, texts: Sequence[str]) -> list[list[float]]:
        missing = list(dict.fromkeys(t for t in texts if t not in self._cache))
        for start in range(0, len(missing), self._batch):
            chunk = missing[start : start + self._batch]
            self._cache.update(zip(chunk, self._provider.embed(self._model, chunk), strict=True))
        return [self._cache[t] for t in texts]


class SemanticCheck:
    def __init__(self, embedder: Embedder, threshold: float = SUPPORT_COSINE) -> None:
        self._embedder = embedder
        self.threshold = threshold

    def similarities(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        """For each (claim, source): the cosine of the claim as a query and the source."""
        claims = self._embedder.vectors([as_query(c) for c, _ in pairs])
        sources = self._embedder.vectors([s for _, s in pairs])
        return [cosine(c, s) for c, s in zip(claims, sources, strict=True)]
