"""Dependency-free TF-IDF retrieval with serializable fitted state."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Protocol

from kathakaar.consistency import ClaimConsistencyGate, ClaimConsistencyResult
from kathakaar.schemas import (
    RetrievalDecision,
    RetrievalHit,
    SourceDocument,
    source_document_from_dict,
)

STOPWORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "at",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "the",
        "through",
        "to",
        "with",
    }
)


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [_stem(word) for word in words if len(word) > 1 and word not in STOPWORDS]


class Retriever(Protocol):
    documents: list[SourceDocument]

    def search(self, query: str, limit: int = 3) -> list[RetrievalHit]:
        """Rank documents for a query."""


class TfidfRetriever:
    """Fit TF-IDF document vectors and rank sources with cosine similarity."""

    def __init__(self) -> None:
        self.documents: list[SourceDocument] = []
        self.idf: dict[str, float] = {}
        self.document_vectors: list[dict[str, float]] = []

    def fit(self, documents: list[SourceDocument]) -> TfidfRetriever:
        if not documents:
            raise ValueError("at least one source document is required")

        self.documents = list(documents)
        document_frequency: Counter[str] = Counter()
        token_counts: list[Counter[str]] = []
        for document in documents:
            counts = Counter(tokenize(_searchable_text(document)))
            token_counts.append(counts)
            document_frequency.update(counts.keys())

        document_count = len(documents)
        self.idf = {
            term: math.log((1 + document_count) / (1 + frequency)) + 1.0
            for term, frequency in document_frequency.items()
        }
        self.document_vectors = [
            _normalize(
                {
                    term: (count / max(1, sum(counts.values()))) * self.idf[term]
                    for term, count in counts.items()
                }
            )
            for counts in token_counts
        ]
        return self

    def search(self, query: str, limit: int = 3) -> list[RetrievalHit]:
        if not self.documents:
            raise RuntimeError("retriever must be fitted before search")
        if limit <= 0:
            return []

        counts = Counter(tokenize(query))
        total = max(1, sum(counts.values()))
        query_vector = _normalize(
            {
                term: (count / total) * self.idf.get(term, 0.0)
                for term, count in counts.items()
                if term in self.idf
            }
        )
        ranked = sorted(
            (
                RetrievalHit(
                    document=document,
                    score=round(_dot(query_vector, vector), 6),
                )
                for document, vector in zip(
                    self.documents,
                    self.document_vectors,
                    strict=True,
                )
            ),
            key=lambda hit: (-hit.score, hit.document.source_id),
        )
        return ranked[:limit]

    def save(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_type": "tfidf",
            "version": 1,
            "documents": [document.to_dict() for document in self.documents],
            "idf": self.idf,
            "document_vectors": self.document_vectors,
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path

    @classmethod
    def load(cls, path: str | Path) -> TfidfRetriever:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("model_type") != "tfidf":
            raise ValueError("unsupported retriever artifact")

        retriever = cls()
        retriever.documents = [
            source_document_from_dict(document) for document in payload["documents"]
        ]
        retriever.idf = {str(term): float(value) for term, value in payload["idf"].items()}
        retriever.document_vectors = [
            {str(term): float(value) for term, value in vector.items()}
            for vector in payload["document_vectors"]
        ]
        return retriever


class BM25Retriever:
    """Serializable Okapi BM25 retriever for sparse cultural-source ranking."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        self.k1 = k1
        self.b = b
        self.documents: list[SourceDocument] = []
        self.document_term_frequencies: list[dict[str, int]] = []
        self.document_lengths: list[int] = []
        self.idf: dict[str, float] = {}
        self.average_document_length = 0.0

    def fit(self, documents: list[SourceDocument]) -> BM25Retriever:
        if not documents:
            raise ValueError("at least one source document is required")

        self.documents = list(documents)
        token_counts = [Counter(tokenize(_searchable_text(document))) for document in documents]
        self.document_term_frequencies = [dict(counts) for counts in token_counts]
        self.document_lengths = [sum(counts.values()) for counts in token_counts]
        self.average_document_length = sum(self.document_lengths) / len(self.document_lengths)

        document_frequency: Counter[str] = Counter()
        for counts in token_counts:
            document_frequency.update(counts.keys())
        document_count = len(documents)
        self.idf = {
            term: math.log(1.0 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }
        return self

    def search(self, query: str, limit: int = 3) -> list[RetrievalHit]:
        if not self.documents:
            raise RuntimeError("retriever must be fitted before search")
        if limit <= 0:
            return []

        query_terms = Counter(tokenize(query))
        hits = []
        for document, term_frequencies, length in zip(
            self.documents,
            self.document_term_frequencies,
            self.document_lengths,
            strict=True,
        ):
            score = sum(
                query_frequency
                * self.idf.get(term, 0.0)
                * self._term_saturation(term_frequencies.get(term, 0), length)
                for term, query_frequency in query_terms.items()
            )
            hits.append(RetrievalHit(document=document, score=round(score, 6)))
        return sorted(
            hits,
            key=lambda hit: (-hit.score, hit.document.source_id),
        )[:limit]

    def save(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_type": "bm25",
            "version": 1,
            "k1": self.k1,
            "b": self.b,
            "documents": [document.to_dict() for document in self.documents],
            "document_term_frequencies": self.document_term_frequencies,
            "document_lengths": self.document_lengths,
            "idf": self.idf,
            "average_document_length": self.average_document_length,
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path

    @classmethod
    def load(cls, path: str | Path) -> BM25Retriever:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("model_type") != "bm25":
            raise ValueError("unsupported retriever artifact")

        retriever = cls(k1=float(payload["k1"]), b=float(payload["b"]))
        retriever.documents = [
            source_document_from_dict(document) for document in payload["documents"]
        ]
        retriever.document_term_frequencies = [
            {str(term): int(value) for term, value in frequencies.items()}
            for frequencies in payload["document_term_frequencies"]
        ]
        retriever.document_lengths = [int(length) for length in payload["document_lengths"]]
        retriever.idf = {str(term): float(value) for term, value in payload["idf"].items()}
        retriever.average_document_length = float(payload["average_document_length"])
        return retriever

    def _term_saturation(self, frequency: int, document_length: int) -> float:
        if frequency == 0:
            return 0.0
        length_ratio = document_length / max(self.average_document_length, 1.0)
        denominator = frequency + self.k1 * (1.0 - self.b + self.b * length_ratio)
        return frequency * (self.k1 + 1.0) / denominator


class HybridRetriever:
    """Fuse TF-IDF and BM25 while enforcing place and evidence constraints."""

    def __init__(self) -> None:
        self.documents: list[SourceDocument] = []
        self.tfidf = TfidfRetriever()
        self.bm25 = BM25Retriever()
        self.claim_gate = ClaimConsistencyGate()

    def fit(self, documents: list[SourceDocument]) -> HybridRetriever:
        if not documents:
            raise ValueError("at least one source document is required")
        self.documents = list(documents)
        self.tfidf.fit(self.documents)
        self.bm25.fit(self.documents)
        return self

    def search(self, query: str, limit: int = 3) -> list[RetrievalHit]:
        return self._rank(query)[: max(0, limit)]

    def assess(
        self,
        query: str,
        place: str,
        limit: int = 3,
        minimum_score: float = 0.2,
        minimum_query_coverage: float = 0.34,
    ) -> RetrievalDecision:
        if not self.documents:
            raise RuntimeError("retriever must be fitted before search")
        if not query.strip():
            return self._rejection("No query text was provided.")

        ranked = self._rank(query)
        place_documents = [hit for hit in ranked if _place_matches(place, hit.document.place)]
        if place.strip() and not place_documents:
            return self._rejection("The fitted corpus has no sources for the requested place.")

        candidates = place_documents if place.strip() else ranked
        if not candidates:
            return self._rejection("No candidate sources were found.")

        selected = candidates[: max(1, limit)]
        top = selected[0]
        second_score = selected[1].score if len(selected) > 1 else 0.0
        query_terms = set(tokenize(query)) - set(tokenize(place))
        evidence_terms = set(tokenize(f"{top.document.title} {top.document.text}"))
        coverage = len(query_terms & evidence_terms) / len(query_terms) if query_terms else 0.0
        place_consistent = not place.strip() or _place_matches(
            place,
            top.document.place,
        )
        consistency = self.claim_gate.evaluate(query, place, selected)

        if top.score < minimum_score:
            reason = "No source reached the minimum fused relevance score."
        elif coverage < minimum_query_coverage:
            reason = "The requested topic is not sufficiently supported for this place."
        elif not place_consistent:
            reason = "The strongest source conflicts with the requested place."
        elif not consistency.supported:
            reason = consistency.reason
        else:
            return RetrievalDecision(
                accepted=True,
                reason=(
                    "Evidence passed relevance, topic coverage, place, and claim checks."
                ),
                top_score=top.score,
                score_margin=round(top.score - second_score, 6),
                query_coverage=round(coverage, 6),
                place_consistent=True,
                hits=tuple(selected),
                claim_gate_applied=consistency.applied,
                claim_consistency_score=consistency.score,
                unsupported_claim_terms=consistency.unsupported_terms,
            )
        return self._rejection(
            reason,
            top_score=top.score,
            score_margin=top.score - second_score,
            query_coverage=coverage,
            place_consistent=place_consistent,
            consistency=consistency,
        )

    def save(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_type": "hybrid_rrf",
            "version": 1,
            "documents": [document.to_dict() for document in self.documents],
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path

    @classmethod
    def load(cls, path: str | Path) -> HybridRetriever:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("model_type") != "hybrid_rrf":
            raise ValueError("unsupported retriever artifact")
        return cls().fit([source_document_from_dict(document) for document in payload["documents"]])

    def _rank(self, query: str) -> list[RetrievalHit]:
        tfidf_hits = self.tfidf.search(query, limit=len(self.documents))
        bm25_hits = self.bm25.search(query, limit=len(self.documents))
        tfidf_scores = _normalized_scores(tfidf_hits)
        bm25_scores = _normalized_scores(bm25_hits)
        explicit_places = {
            _place_key(document.place)
            for document in self.documents
            if _place_key(document.place) in _normalize_text(query)
        }

        hits = []
        for document in self.documents:
            score = 0.55 * tfidf_scores.get(document.source_id, 0.0) + 0.45 * bm25_scores.get(
                document.source_id, 0.0
            )
            if explicit_places:
                score *= 1.25 if _place_key(document.place) in explicit_places else 0.45
            hits.append(RetrievalHit(document=document, score=round(score, 6)))
        return sorted(hits, key=lambda hit: (-hit.score, hit.document.source_id))

    @staticmethod
    def _rejection(
        reason: str,
        top_score: float = 0.0,
        score_margin: float = 0.0,
        query_coverage: float = 0.0,
        place_consistent: bool = False,
        consistency: ClaimConsistencyResult | None = None,
    ) -> RetrievalDecision:
        consistency = consistency or ClaimConsistencyResult.skipped()
        return RetrievalDecision(
            accepted=False,
            reason=reason,
            top_score=round(top_score, 6),
            score_margin=round(score_margin, 6),
            query_coverage=round(query_coverage, 6),
            place_consistent=place_consistent,
            hits=(),
            claim_gate_applied=consistency.applied,
            claim_consistency_score=consistency.score,
            unsupported_claim_terms=consistency.unsupported_terms,
        )


def load_retriever(path: str | Path) -> Retriever:
    model_path = Path(path)
    payload = json.loads(model_path.read_text(encoding="utf-8"))
    model_type = payload.get("model_type")
    if model_type == "tfidf":
        return TfidfRetriever.load(model_path)
    if model_type == "bm25":
        return BM25Retriever.load(model_path)
    if model_type == "hybrid_rrf":
        return HybridRetriever.load(model_path)
    raise ValueError(f"unsupported retriever artifact: {model_type!r}")


def load_corpus(path: str | Path) -> list[SourceDocument]:
    corpus_path = Path(path)
    documents: list[SourceDocument] = []
    for line in corpus_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            documents.append(source_document_from_dict(json.loads(line)))
    if not documents:
        raise ValueError(f"source corpus is empty: {corpus_path}")
    return documents


def _searchable_text(document: SourceDocument) -> str:
    media_text = " ".join(
        f"{asset.caption} {asset.transcript} {asset.creator}" for asset in document.media_assets
    )
    return (
        f"{document.title} {document.place} {document.country} {document.period} "
        f"{document.text} {media_text}"
    )


def _normalize(vector: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm == 0:
        return vector
    return {term: value / norm for term, value in vector.items()}


def _dot(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(term, 0.0) for term, value in left.items())


def _stem(word: str) -> str:
    if len(word) > 5 and word.endswith("ies"):
        return f"{word[:-3]}y"
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _normalized_scores(hits: list[RetrievalHit]) -> dict[str, float]:
    maximum = max((hit.score for hit in hits), default=0.0)
    if maximum <= 0:
        return {hit.document.source_id: 0.0 for hit in hits}
    return {hit.document.source_id: hit.score / maximum for hit in hits}


def _normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _place_key(place: str) -> str:
    return _normalize_text(place.split(",", maxsplit=1)[0])


def _place_matches(requested: str, documented: str) -> bool:
    if not requested.strip():
        return True
    requested_key = _place_key(requested)
    documented_key = _place_key(documented)
    return requested_key == documented_key
