"""Typed data contracts for retrieval, generation, and evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MediaAsset:
    asset_id: str
    media_type: str
    url: str
    mime_type: str = ""
    caption: str = ""
    transcript: str = ""
    creator: str = ""
    license: str = ""
    rights_status: str = "unknown"
    attribution: str = ""
    local_path: str = ""
    sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceDocument:
    source_id: str
    title: str
    place: str
    url: str
    text: str
    publisher: str = ""
    license: str = ""
    retrieved_at: str = ""
    language: str = "en"
    country: str = ""
    period: str = ""
    source_kind: str = "cultural_record"
    rights_uri: str = ""
    rights_status: str = "unknown"
    attribution: str = ""
    content_hash: str = ""
    review_status: str = "unreviewed"
    coordinates: tuple[float, float] | None = None
    media_assets: tuple[MediaAsset, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["media_assets"] = [asset.to_dict() for asset in self.media_assets]
        payload["coordinates"] = list(self.coordinates) if self.coordinates else None
        return payload


@dataclass(frozen=True)
class RetrievalHit:
    document: SourceDocument
    score: float
    modality_scores: dict[str, float] = field(default_factory=dict)
    matched_asset_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document.to_dict(),
            "score": self.score,
            "modality_scores": self.modality_scores,
            "matched_asset_ids": list(self.matched_asset_ids),
        }


@dataclass(frozen=True)
class RetrievalDecision:
    accepted: bool
    reason: str
    top_score: float
    score_margin: float
    query_coverage: float
    place_consistent: bool
    hits: tuple[RetrievalHit, ...]
    claim_gate_applied: bool = False
    claim_consistency_score: float = 1.0
    unsupported_claim_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "top_score": self.top_score,
            "score_margin": self.score_margin,
            "query_coverage": self.query_coverage,
            "place_consistent": self.place_consistent,
            "hits": [hit.to_dict() for hit in self.hits],
            "claim_gate_applied": self.claim_gate_applied,
            "claim_consistency_score": self.claim_consistency_score,
            "unsupported_claim_terms": list(self.unsupported_claim_terms),
        }


@dataclass(frozen=True)
class GroundedClaim:
    text: str
    source_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "source_ids": list(self.source_ids)}


@dataclass(frozen=True)
class StoryResult:
    title: str
    narrative: str
    claims: tuple[GroundedClaim, ...]
    sources: tuple[SourceDocument, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "narrative": self.narrative,
            "claims": [claim.to_dict() for claim in self.claims],
            "sources": [source.to_dict() for source in self.sources],
        }


@dataclass(frozen=True)
class RAGResult:
    status: str
    retrieval: RetrievalDecision
    story: StoryResult | None
    generator: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "retrieval": self.retrieval.to_dict(),
            "story": self.story.to_dict() if self.story else None,
            "generator": self.generator,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class BenchmarkQuery:
    query_id: str
    query: str
    place: str
    expected_source_ids: tuple[str, ...]
    theme: str
    should_abstain: bool = False


def source_document_from_dict(payload: dict[str, Any]) -> SourceDocument:
    """Load current or legacy source records into the normalized schema."""
    normalized = dict(payload)
    normalized["media_assets"] = tuple(
        asset if isinstance(asset, MediaAsset) else MediaAsset(**asset)
        for asset in normalized.get("media_assets", ())
    )
    coordinates = normalized.get("coordinates")
    if coordinates is not None:
        normalized["coordinates"] = (float(coordinates[0]), float(coordinates[1]))
    return SourceDocument(**normalized)
