"""Okapi BM25 over short texts, for choosing which parts of a long meeting to show the model.
Words are cut to five characters, like the grounding checker's keys."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from evra.notes.validate import STOPWORDS

_WORD = re.compile(r"\w+")
STEM = 5


def tokenize(text: str) -> list[str]:
    words = _WORD.findall(text.lower())
    return [w[:STEM] for w in words if len(w) > 1 and not w.isdigit() and w not in STOPWORDS]


class Bm25:
    def __init__(
        self, documents: Sequence[Sequence[str]], *, k1: float = 1.5, b: float = 0.75
    ) -> None:
        self._k1, self._b = k1, b
        self._counts = [Counter(d) for d in documents]
        self._lengths = [len(d) for d in documents]
        n = len(documents)
        self._avg = sum(self._lengths) / n if n else 0.0
        frequency: Counter[str] = Counter()
        for counts in self._counts:
            frequency.update(counts.keys())
        self._idf = {t: math.log(1 + (n - df + 0.5) / (df + 0.5)) for t, df in frequency.items()}

    def scores(self, query: Sequence[str]) -> list[float]:
        terms = set(query)
        result: list[float] = []
        for counts, length in zip(self._counts, self._lengths, strict=True):
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if not tf:
                    continue
                norm = 1 - self._b + self._b * (length / self._avg if self._avg else 0.0)
                score += self._idf[term] * tf * (self._k1 + 1) / (tf + self._k1 * norm)
            result.append(score)
        return result
