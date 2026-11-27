"""Meaning-based checks with embeddings (BUILD.md D17, changed 2026-11-26: through Ollama).

Qwen3-Embedding wants an instruction on the query side only; documents carry none. Vectors
arrive at unit length, so the cosine is a dot product.
"""

from __future__ import annotations

from collections.abc import Sequence
from threading import Lock

from evra.llm.provider import LlmProvider

# the smallest candidate at which at most 2% of mismatched pairs pass, measured by
# tools/calibrate_semantic.py (DECISIONS.md "Meaning check threshold", 2026-11-26)
SUPPORT_COSINE = 0.55
QUERY_TASK = "Given a statement from meeting notes, retrieve the transcript lines that say it"


def as_query(text: str, task: str = QUERY_TASK) -> str:
    return f"Instruct: {task}\nQuery:{text}"


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class Embedder:
    """Embeds texts in batches; each distinct text is embedded once per instance. Callers on
    one instance take turns (the Ask tab's pre-read and a question about the same meeting), so
    a text another caller is embedding is never embedded twice."""

    def __init__(self, provider: LlmProvider, model: str, *, batch: int = 64) -> None:
        self._provider = provider
        self._model = model
        self._batch = batch
        self._cache: dict[str, list[float]] = {}
        self._lock = Lock()

    def vectors(self, texts: Sequence[str]) -> list[list[float]]:
        with self._lock:
            missing = list(dict.fromkeys(t for t in texts if t not in self._cache))
            for start in range(0, len(missing), self._batch):
                chunk = missing[start : start + self._batch]
                vectors = self._provider.embed(self._model, chunk)
                self._cache.update(zip(chunk, vectors, strict=True))
            return [self._cache[t] for t in texts]


class SemanticCheck:
    def __init__(self, embedder: Embedder, threshold: float = SUPPORT_COSINE) -> None:
        self._embedder = embedder
        self.threshold = threshold

    @property
    def embedder(self) -> Embedder:
        """Its embedder, for a step of the same job that embeds first (linking typed notes)."""
        return self._embedder

    def similarities(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        """For each (claim, source): the cosine of the claim as a query and the source. Claims
        and sources go in one batch, so a few pairs are one embedding request."""
        vectors = self._embedder.vectors([*(as_query(c) for c, _ in pairs), *(s for _, s in pairs)])
        claims, sources = vectors[: len(pairs)], vectors[len(pairs) :]
        return [cosine(c, s) for c, s in zip(claims, sources, strict=True)]
