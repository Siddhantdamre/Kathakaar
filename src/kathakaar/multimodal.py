"""Multimodal retrieval with a deterministic fallback and optional SigLIP encoder."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
from pathlib import Path
from typing import Protocol

from kathakaar.consistency import ClaimConsistencyGate, ClaimConsistencyResult
from kathakaar.net import download_bytes
from kathakaar.retrieval import HybridRetriever, tokenize
from kathakaar.schemas import (
    MediaAsset,
    RetrievalDecision,
    RetrievalHit,
    SourceDocument,
    source_document_from_dict,
)


class MultimodalEncoder(Protocol):
    name: str
    dimensions: int

    def encode_text(self, text: str) -> list[float]:
        """Encode a natural-language query."""

    def encode_asset(self, asset: MediaAsset) -> list[float]:
        """Encode an image, audio, video, or document asset."""


class HashingMultimodalEncoder:
    """Dependency-free fallback over captions, transcripts, and media metadata."""

    name = "hashing-metadata-v1"

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions < 32:
            raise ValueError("dimensions must be at least 32")
        self.dimensions = dimensions

    def encode_text(self, text: str) -> list[float]:
        return self._encode_tokens(tokenize(text))

    def encode_asset(self, asset: MediaAsset) -> list[float]:
        text = " ".join(
            (
                asset.media_type,
                asset.mime_type,
                asset.caption,
                asset.transcript,
                asset.creator,
                asset.attribution,
            )
        )
        return self._encode_tokens(tokenize(text))

    def _encode_tokens(self, tokens: list[str]) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        return _normalize_dense(vector)


class SiglipMultimodalEncoder:
    """Optional pretrained image-text encoder for genuine visual retrieval."""

    name = "siglip"

    def __init__(
        self,
        model_id: str = "google/siglip-base-patch16-224",
        timeout_seconds: float = 30.0,
    ) -> None:
        try:
            import torch  # type: ignore[import-not-found]
            from transformers import AutoModel, AutoProcessor  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("Install kathakaar[multimodal] to use the SigLIP encoder.") from exc

        self._torch = torch
        self._processor = AutoProcessor.from_pretrained(model_id)
        self._model = AutoModel.from_pretrained(model_id)
        self._model.eval()
        self.timeout_seconds = timeout_seconds
        self.dimensions = int(getattr(self._model.config, "projection_size", 768))
        self.name = f"siglip:{model_id}"

    def encode_text(self, text: str) -> list[float]:
        inputs = self._processor(text=[text], padding="max_length", return_tensors="pt")
        with self._torch.no_grad():
            features = self._model.get_text_features(**inputs)
        return _normalize_dense(features[0].cpu().tolist())

    def encode_asset(self, asset: MediaAsset) -> list[float]:
        if asset.media_type != "image":
            return self.encode_text(" ".join((asset.caption, asset.transcript, asset.creator)))
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Install kathakaar[multimodal] to load image assets.") from exc

        image_bytes = self._read_asset(asset)
        with Image.open(io.BytesIO(image_bytes)) as image:
            inputs = self._processor(images=image.convert("RGB"), return_tensors="pt")
        with self._torch.no_grad():
            features = self._model.get_image_features(**inputs)
        return _normalize_dense(features[0].cpu().tolist())

    def _read_asset(self, asset: MediaAsset) -> bytes:
        if asset.local_path:
            return Path(asset.local_path).read_bytes()
        return download_bytes(
            asset.url,
            headers={"User-Agent": "Kathakaar/0.3 (multimodal research prototype)"},
            timeout_seconds=self.timeout_seconds,
        )


class MultimodalRetriever:
    """Fuse lexical evidence with image/audio/video metadata or neural embeddings."""

    def __init__(
        self,
        encoder: MultimodalEncoder | None = None,
        text_weight: float = 0.72,
        media_weight: float = 0.28,
    ) -> None:
        if text_weight < 0 or media_weight < 0 or text_weight + media_weight <= 0:
            raise ValueError("retrieval weights must be non-negative and non-zero")
        total = text_weight + media_weight
        self.text_weight = text_weight / total
        self.media_weight = media_weight / total
        self.encoder = encoder or HashingMultimodalEncoder()
        self.documents: list[SourceDocument] = []
        self.text_retriever = HybridRetriever()
        self.claim_gate = ClaimConsistencyGate()
        self.asset_vectors: dict[str, list[float]] = {}
        self.asset_lookup: dict[str, tuple[str, MediaAsset]] = {}

    def fit(self, documents: list[SourceDocument]) -> MultimodalRetriever:
        if not documents:
            raise ValueError("at least one source document is required")
        self.documents = list(documents)
        self.text_retriever.fit(self.documents)
        self.asset_vectors.clear()
        self.asset_lookup.clear()
        for document in self.documents:
            for asset in document.media_assets:
                vector = self.encoder.encode_asset(asset)
                if vector:
                    self.asset_vectors[asset.asset_id] = vector
                    self.asset_lookup[asset.asset_id] = (document.source_id, asset)
        return self

    def search(
        self,
        query: str,
        limit: int = 3,
        place: str = "",
        query_asset: MediaAsset | None = None,
    ) -> list[RetrievalHit]:
        if not self.documents:
            raise RuntimeError("retriever must be fitted before search")
        if limit <= 0:
            return []

        text_hits = self.text_retriever.search(query, limit=len(self.documents))
        text_scores = _normalized_hit_scores(text_hits)
        query_vector = (
            self.encoder.encode_asset(query_asset)
            if query_asset is not None
            else self.encoder.encode_text(query)
        )

        hits: list[RetrievalHit] = []
        for document in self.documents:
            if place and not _place_matches(place, document.place):
                continue
            media_scores = [
                _cosine_dense(query_vector, vector)
                for asset_id, vector in self.asset_vectors.items()
                if self.asset_lookup[asset_id][0] == document.source_id
            ]
            best_media_score = max(media_scores, default=0.0)
            matched_assets = tuple(
                asset_id
                for asset_id, vector in self.asset_vectors.items()
                if self.asset_lookup[asset_id][0] == document.source_id
                and _cosine_dense(query_vector, vector) == best_media_score
                and best_media_score > 0
            )
            text_score = text_scores.get(document.source_id, 0.0)
            if query_asset is not None:
                score = 0.2 * text_score + 0.8 * best_media_score
            else:
                score = self.text_weight * text_score + self.media_weight * best_media_score
            hits.append(
                RetrievalHit(
                    document=document,
                    score=round(score, 6),
                    modality_scores={
                        "text": round(text_score, 6),
                        "media": round(best_media_score, 6),
                    },
                    matched_asset_ids=matched_assets[:3],
                )
            )
        return sorted(hits, key=lambda hit: (-hit.score, hit.document.source_id))[:limit]

    def assess(
        self,
        query: str,
        place: str,
        limit: int = 3,
        query_asset: MediaAsset | None = None,
        minimum_score: float = 0.2,
        minimum_query_coverage: float = 0.34,
    ) -> RetrievalDecision:
        if place and not any(_place_matches(place, doc.place) for doc in self.documents):
            return _rejection("The knowledge base has no records for the requested place.")

        hits = self.search(
            query,
            limit=max(2, limit),
            place=place,
            query_asset=query_asset,
        )
        if not hits:
            return _rejection("No candidate records were found.")

        top = hits[0]
        second_score = hits[1].score if len(hits) > 1 else 0.0
        query_terms = set(tokenize(query)) - set(tokenize(place))
        evidence_terms = set(
            tokenize(
                " ".join(
                    (
                        top.document.title,
                        top.document.text,
                        " ".join(
                            f"{asset.caption} {asset.transcript}"
                            for asset in top.document.media_assets
                        ),
                    )
                )
            )
        )
        coverage = (
            len(query_terms & evidence_terms) / len(query_terms)
            if query_terms
            else float(query_asset is not None)
        )
        place_consistent = not place or _place_matches(place, top.document.place)
        selected = hits[: max(1, limit)]
        consistency = self.claim_gate.evaluate(query, place, selected)

        if top.score < minimum_score:
            reason = "No record reached the multimodal relevance threshold."
        elif query_asset is None and coverage < minimum_query_coverage:
            reason = "The requested topic is not sufficiently supported for this place."
        elif not place_consistent:
            reason = "The strongest record conflicts with the requested place."
        elif not consistency.supported:
            reason = consistency.reason
        else:
            return RetrievalDecision(
                accepted=True,
                reason="Evidence passed text, media, topic, place, and claim checks.",
                top_score=top.score,
                score_margin=round(top.score - second_score, 6),
                query_coverage=round(coverage, 6),
                place_consistent=True,
                hits=tuple(selected),
                claim_gate_applied=consistency.applied,
                claim_consistency_score=consistency.score,
                unsupported_claim_terms=consistency.unsupported_terms,
            )
        return _rejection(
            reason,
            top_score=top.score,
            score_margin=top.score - second_score,
            coverage=coverage,
            place_consistent=place_consistent,
            consistency=consistency,
        )

    def save(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model_type": "multimodal_hybrid",
            "version": 3,
            "encoder": self.encoder.name,
            "dimensions": self.encoder.dimensions,
            "text_weight": self.text_weight,
            "media_weight": self.media_weight,
            "documents": [document.to_dict() for document in self.documents],
            "asset_vectors": self.asset_vectors,
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path

    @classmethod
    def load(
        cls,
        path: str | Path,
        encoder: MultimodalEncoder | None = None,
    ) -> MultimodalRetriever:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("model_type") != "multimodal_hybrid":
            raise ValueError("unsupported multimodal retriever artifact")
        encoder_name = str(payload.get("encoder", ""))
        if encoder is None:
            if encoder_name != HashingMultimodalEncoder.name:
                raise ValueError(
                    f"artifact requires encoder {encoder_name!r}; pass a compatible encoder"
                )
            encoder = HashingMultimodalEncoder(int(payload["dimensions"]))
        retriever = cls(
            encoder=encoder,
            text_weight=float(payload["text_weight"]),
            media_weight=float(payload["media_weight"]),
        )
        retriever.documents = [
            source_document_from_dict(document) for document in payload["documents"]
        ]
        retriever.text_retriever.fit(retriever.documents)
        retriever.asset_vectors = {
            str(asset_id): [float(value) for value in vector]
            for asset_id, vector in payload["asset_vectors"].items()
        }
        retriever.asset_lookup = {
            asset.asset_id: (document.source_id, asset)
            for document in retriever.documents
            for asset in document.media_assets
            if asset.asset_id in retriever.asset_vectors
        }
        return retriever


def query_asset_from_path(path: str | Path) -> MediaAsset:
    image_path = Path(path).resolve()
    if not image_path.exists():
        raise FileNotFoundError(image_path)
    mime_type = _guess_mime_type(image_path)
    return MediaAsset(
        asset_id=f"query-{hashlib.sha256(str(image_path).encode()).hexdigest()[:12]}",
        media_type=mime_type.split("/", maxsplit=1)[0],
        url="",
        local_path=str(image_path),
        mime_type=mime_type,
        caption=image_path.stem.replace("_", " "),
        rights_status="link_only",
    )


def _guess_mime_type(path: Path) -> str:
    suffixes = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".mp4": "video/mp4",
        ".pdf": "application/pdf",
    }
    return suffixes.get(path.suffix.lower(), "application/octet-stream")


def _normalized_hit_scores(hits: list[RetrievalHit]) -> dict[str, float]:
    maximum = max((hit.score for hit in hits), default=0.0)
    if maximum <= 0:
        return {hit.document.source_id: 0.0 for hit in hits}
    return {hit.document.source_id: hit.score / maximum for hit in hits}


def _normalize_dense(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _cosine_dense(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    return max(0.0, sum(a * b for a, b in zip(left, right, strict=True)))


def _place_matches(requested: str, documented: str) -> bool:
    def normalize(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))

    return normalize(requested.split(",", maxsplit=1)[0]) == normalize(
        documented.split(",", maxsplit=1)[0]
    )


def _rejection(
    reason: str,
    top_score: float = 0.0,
    score_margin: float = 0.0,
    coverage: float = 0.0,
    place_consistent: bool = False,
    consistency: ClaimConsistencyResult | None = None,
) -> RetrievalDecision:
    consistency = consistency or ClaimConsistencyResult.skipped()
    return RetrievalDecision(
        accepted=False,
        reason=reason,
        top_score=round(top_score, 6),
        score_margin=round(score_margin, 6),
        query_coverage=round(coverage, 6),
        place_consistent=place_consistent,
        hits=(),
        claim_gate_applied=consistency.applied,
        claim_consistency_score=consistency.score,
        unsupported_claim_terms=consistency.unsupported_terms,
    )
