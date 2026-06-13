"""Transparent consistency checks for declarative retrieval queries."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from kathakaar.schemas import RetrievalHit

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_QUESTION_PREFIXES = frozenset(
    {
        "can",
        "could",
        "describe",
        "explain",
        "find",
        "give",
        "how",
        "show",
        "tell",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "would",
    }
)
_ASSERTION_MARKERS = frozenset(
    {
        "are",
        "became",
        "belongs",
        "built",
        "commissioned",
        "constructed",
        "contains",
        "created",
        "designed",
        "destroyed",
        "discovered",
        "founded",
        "had",
        "has",
        "have",
        "imported",
        "included",
        "is",
        "located",
        "made",
        "powered",
        "preserves",
        "served",
        "stands",
        "used",
        "was",
        "were",
    }
)
_CONTENT_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "for",
        "from",
        "had",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "that",
        "the",
        "their",
        "there",
        "these",
        "this",
        "those",
        "to",
        "was",
        "were",
        "with",
    }
)


@dataclass(frozen=True)
class ClaimConsistencyResult:
    """Auditable result from comparing an asserted claim with retrieved evidence."""

    applied: bool
    supported: bool
    score: float
    unsupported_terms: tuple[str, ...]
    reason: str

    @classmethod
    def skipped(cls) -> ClaimConsistencyResult:
        return cls(
            applied=False,
            supported=True,
            score=1.0,
            unsupported_terms=(),
            reason="Query is not a declarative factual claim.",
        )


class ClaimConsistencyGate:
    """Reject declarative claims whose content is not supported by retrieved records."""

    def __init__(self, minimum_support: float = 1.0) -> None:
        if not 0.0 <= minimum_support <= 1.0:
            raise ValueError("minimum_support must be between 0 and 1")
        self.minimum_support = minimum_support

    def evaluate(
        self,
        query: str,
        place: str,
        hits: Sequence[RetrievalHit],
    ) -> ClaimConsistencyResult:
        if not _looks_declarative(query):
            return ClaimConsistencyResult.skipped()

        place_terms = set(_content_terms(place))
        query_terms = [
            term for term in _content_terms(query) if term not in place_terms
        ]
        if not query_terms:
            return ClaimConsistencyResult(
                applied=True,
                supported=False,
                score=0.0,
                unsupported_terms=(),
                reason="The factual claim contains no verifiable content terms.",
            )

        evidence_terms = set(
            _content_terms(" ".join(_evidence_text(hit) for hit in hits))
        )
        unsupported = _ordered_unique(
            term for term in query_terms if term not in evidence_terms
        )
        score = (len(query_terms) - len(unsupported)) / len(query_terms)
        supported = score >= self.minimum_support

        if supported:
            reason = "Declarative claim terms are supported by the retrieved evidence."
        else:
            terms = ", ".join(unsupported) if unsupported else "unspecified relation"
            reason = f"Retrieved evidence does not support claim terms: {terms}."
        return ClaimConsistencyResult(
            applied=True,
            supported=supported,
            score=round(score, 6),
            unsupported_terms=unsupported,
            reason=reason,
        )


def _looks_declarative(text: str) -> bool:
    stripped = text.strip()
    tokens = [match.group(0).lower() for match in _TOKEN_PATTERN.finditer(stripped)]
    if not tokens or stripped.endswith("?") or tokens[0] in _QUESTION_PREFIXES:
        return False
    return any(token in _ASSERTION_MARKERS for token in tokens)


def _content_terms(text: str) -> list[str]:
    terms = []
    for match in _TOKEN_PATTERN.finditer(text):
        token = match.group(0).lower()
        if len(token) <= 1 or token in _CONTENT_STOPWORDS:
            continue
        terms.append(_stem(token))
    return terms


def _evidence_text(hit: RetrievalHit) -> str:
    document = hit.document
    media_text = " ".join(
        f"{asset.caption} {asset.transcript} {asset.creator}"
        for asset in document.media_assets
    )
    return " ".join(
        (
            document.title,
            document.place,
            document.country,
            document.period,
            document.text,
            media_text,
        )
    )


def _ordered_unique(terms: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(terms))


def _stem(word: str) -> str:
    if len(word) > 5 and word.endswith("ies"):
        return f"{word[:-3]}y"
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word
