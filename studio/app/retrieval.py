"""BM25 retrieval over the cultural corpus (standard library only)."""
from __future__ import annotations

import math
import re
from collections import Counter

from .grounding import Source


def _tok(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.sources: list[Source] = []
        self._docs: list[list[str]] = []
        self._idf: dict[str, float] = {}
        self._avgdl = 0.0

    def fit(self, sources: list[Source]) -> "BM25":
        self.sources = list(sources)
        self._docs = [_tok(s.text + " " + s.title + " " + s.place) for s in self.sources]
        n = len(self._docs)
        df: Counter[str] = Counter()
        for d in self._docs:
            for t in set(d):
                df[t] += 1
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self._avgdl = (sum(len(d) for d in self._docs) / n) if n else 0.0
        return self

    def _score(self, q: list[str], doc: list[str]) -> float:
        if not doc:
            return 0.0
        counts = Counter(doc)
        dl = len(doc)
        out = 0.0
        for t in q:
            if t not in counts:
                continue
            idf = self._idf.get(t, 0.0)
            tf = counts[t]
            out += idf * (tf * (self.k1 + 1)) / (
                tf + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1.0))
            )
        return out

    def search(self, query: str, k: int = 3) -> list[tuple[Source, float]]:
        q = _tok(query)
        scored = [(self.sources[i], self._score(q, d)) for i, d in enumerate(self._docs)]
        scored = [(s, round(sc, 4)) for s, sc in scored if sc > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]
