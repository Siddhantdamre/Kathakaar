"""Guarded retrieval-augmented generation with claim-level source validation."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol
from urllib.request import Request, urlopen

from kathakaar.generation import GroundedStoryGenerator
from kathakaar.multimodal import MultimodalRetriever
from kathakaar.retrieval import tokenize
from kathakaar.schemas import (
    GroundedClaim,
    MediaAsset,
    RAGResult,
    RetrievalHit,
    SourceDocument,
    StoryResult,
)


class StoryGenerator(Protocol):
    name: str

    def generate(
        self,
        place: str,
        theme: str,
        hits: list[RetrievalHit],
        max_claims: int = 4,
    ) -> StoryResult:
        """Generate a story using only retrieved evidence."""


class ChatBackend(Protocol):
    name: str

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Return a model response."""


class ExtractiveStoryGenerator:
    name = "extractive"

    def __init__(self) -> None:
        self._generator = GroundedStoryGenerator()

    def generate(
        self,
        place: str,
        theme: str,
        hits: list[RetrievalHit],
        max_claims: int = 4,
    ) -> StoryResult:
        return self._generator.generate(place, theme, hits, max_claims=max_claims)


class OllamaChatBackend:
    """Minimal Ollama chat adapter with no mandatory Python dependency."""

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.name = f"ollama:{model}"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"temperature": 0.2},
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/chat",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
        return str(result["message"]["content"])


class StructuredGenAIStoryGenerator:
    """Use a chat model, then reject uncited or weakly supported claims."""

    def __init__(
        self,
        backend: ChatBackend,
        minimum_claim_support: float = 0.35,
    ) -> None:
        self.backend = backend
        self.minimum_claim_support = minimum_claim_support
        self.name = f"structured-genai:{backend.name}"

    def generate(
        self,
        place: str,
        theme: str,
        hits: list[RetrievalHit],
        max_claims: int = 4,
    ) -> StoryResult:
        if not hits:
            raise ValueError("no retrieved evidence was supplied")
        source_lookup = {hit.document.source_id: hit.document for hit in hits}
        source_bundle = [
            {
                "source_id": hit.document.source_id,
                "title": hit.document.title,
                "place": hit.document.place,
                "text": hit.document.text,
                "media_captions": [
                    asset.caption for asset in hit.document.media_assets if asset.caption
                ],
            }
            for hit in hits
        ]
        response = self.backend.complete(
            system_prompt=(
                "You are a cultural heritage writer. Use only the supplied sources. "
                "Return JSON with title and claims. Each claim must have text and "
                "source_ids. Do not invent dialogue, motives, dates, or traditions. "
                "Interpretation must be explicitly labeled as interpretation."
            ),
            user_prompt=json.dumps(
                {
                    "place": place,
                    "theme": theme,
                    "maximum_claims": max_claims,
                    "sources": source_bundle,
                    "output_schema": {
                        "title": "string",
                        "claims": [
                            {
                                "text": "string",
                                "source_ids": ["retrieved source id"],
                            }
                        ],
                    },
                },
                ensure_ascii=True,
            ),
        )
        payload = _parse_json_object(response)
        raw_claims = payload.get("claims")
        if not isinstance(raw_claims, list) or not raw_claims:
            raise ValueError("generator returned no structured claims")

        claims: list[GroundedClaim] = []
        for item in raw_claims[:max_claims]:
            if not isinstance(item, dict):
                raise ValueError("generator returned a malformed claim")
            text = str(item.get("text", "")).strip()
            source_ids = tuple(str(value) for value in item.get("source_ids", []))
            if not text or not source_ids:
                raise ValueError("every generated claim must contain text and citations")
            if any(source_id not in source_lookup for source_id in source_ids):
                raise ValueError("generator cited a source that was not retrieved")
            claim = GroundedClaim(text=text, source_ids=source_ids)
            support = _claim_support(claim, source_lookup)
            if support < self.minimum_claim_support:
                raise ValueError(f"generated claim failed support threshold: {support:.3f}")
            claims.append(claim)

        cited_ids = tuple(
            dict.fromkeys(source_id for claim in claims for source_id in claim.source_ids)
        )
        title = str(payload.get("title") or f"{place}: {theme.title()}").strip()
        return StoryResult(
            title=title,
            narrative=_render_grounded_narrative(place, theme, tuple(claims)),
            claims=tuple(claims),
            sources=tuple(source_lookup[source_id] for source_id in cited_ids),
        )


class GuardedMultimodalRAG:
    """Retrieve, abstain when necessary, and generate only from accepted evidence."""

    def __init__(
        self,
        retriever: MultimodalRetriever,
        generator: StoryGenerator | None = None,
    ) -> None:
        self.retriever = retriever
        self.generator = generator or ExtractiveStoryGenerator()

    def answer(
        self,
        query: str,
        place: str,
        theme: str,
        limit: int = 4,
        query_asset: MediaAsset | None = None,
    ) -> RAGResult:
        decision = self.retriever.assess(
            query=query,
            place=place,
            limit=limit,
            query_asset=query_asset,
        )
        if not decision.accepted:
            return RAGResult(
                status="insufficient_evidence",
                retrieval=decision,
                story=None,
                generator=self.generator.name,
                warnings=("No narrative was generated because retrieval abstained.",),
            )
        try:
            story = self.generator.generate(
                place=place,
                theme=theme,
                hits=list(decision.hits),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return RAGResult(
                status="generation_rejected",
                retrieval=decision,
                story=None,
                generator=self.generator.name,
                warnings=(str(exc),),
            )
        return RAGResult(
            status="grounded",
            retrieval=decision,
            story=story,
            generator=self.generator.name,
        )


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("generator did not return a JSON object") from None
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("generator response must be a JSON object")
    return value


def _claim_support(
    claim: GroundedClaim,
    source_lookup: dict[str, SourceDocument],
) -> float:
    claim_terms = set(tokenize(claim.text))
    if not claim_terms:
        return 0.0
    source_terms: set[str] = set()
    for source_id in claim.source_ids:
        source = source_lookup[source_id]
        source_terms.update(tokenize(source.text))
        for asset in source.media_assets:
            source_terms.update(tokenize(f"{asset.caption} {asset.transcript}"))
    return len(claim_terms & source_terms) / len(claim_terms)


def _render_grounded_narrative(
    place: str,
    theme: str,
    claims: tuple[GroundedClaim, ...],
) -> str:
    paragraphs = [f"{place}, explored through {theme}."]
    for claim in claims:
        citations = ", ".join(f"[{source_id}]" for source_id in claim.source_ids)
        paragraphs.append(f"{claim.text} {citations}")
    paragraphs.append("Kathakaar generated this narrative only from the cited retrieved evidence.")
    return "\n\n".join(paragraphs)
