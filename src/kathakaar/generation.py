"""Citation-aware extractive cultural story generation."""

from __future__ import annotations

import re

from kathakaar.retrieval import tokenize
from kathakaar.schemas import GroundedClaim, RetrievalHit, StoryResult


class GroundedStoryGenerator:
    """Create a readable narrative while keeping factual claims source-linked."""

    def generate(
        self,
        place: str,
        theme: str,
        hits: list[RetrievalHit],
        max_claims: int = 4,
    ) -> StoryResult:
        usable_hits = [hit for hit in hits if hit.score > 0]
        if not usable_hits:
            raise ValueError("no relevant sources were retrieved")

        query_terms = set(tokenize(f"{place} {theme}"))
        candidates: list[tuple[float, str, str]] = []
        for hit in usable_hits:
            for sentence in _sentences(hit.document.text):
                sentence_terms = set(tokenize(sentence))
                relevance = len(query_terms & sentence_terms) + hit.score
                candidates.append((relevance, sentence, hit.document.source_id))

        selected: list[tuple[str, str]] = []
        seen: set[str] = set()
        for _, sentence, source_id in sorted(
            candidates,
            key=lambda item: (-item[0], item[2], item[1]),
        ):
            normalized = sentence.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append((sentence, source_id))
            if len(selected) >= max_claims:
                break

        claims = tuple(
            GroundedClaim(text=sentence, source_ids=(source_id,))
            for sentence, source_id in selected
        )
        source_lookup = {hit.document.source_id: hit.document for hit in usable_hits}
        cited_sources = tuple(
            source_lookup[source_id]
            for source_id in dict.fromkeys(
                source_id for claim in claims for source_id in claim.source_ids
            )
        )
        narrative = _render_narrative(place, theme, claims)
        return StoryResult(
            title=f"{place}: {theme.title()}",
            narrative=narrative,
            claims=claims,
            sources=cited_sources,
        )


def _sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
        if len(sentence.strip()) >= 20
    ]


def _render_narrative(
    place: str,
    theme: str,
    claims: tuple[GroundedClaim, ...],
) -> str:
    opening = f"Kathakaar opens the archive of {place} through the theme of {theme}."
    paragraphs = [opening]
    for claim in claims:
        citations = ", ".join(f"[{source_id}]" for source_id in claim.source_ids)
        paragraphs.append(f"{claim.text} {citations}")
    paragraphs.append(
        "This is an extractive, source-grounded narrative; interpretation is kept "
        "separate from the cited historical claims."
    )
    return "\n\n".join(paragraphs)
