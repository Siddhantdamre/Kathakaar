"""Deterministic, fully-grounded story composer.

Every sentence in the output is selected from a retrieved source, so the story
is grounded by construction; the grounding layer then verifies and cites it.
No LLM, no API keys -> reproducible and deployable anywhere.
"""
from __future__ import annotations

from . import genai
from .grounding import Source, ground, split_sentences, tokens


def _city(place: str | None) -> set[str]:
    """Tokens of the city part only (text before the first comma)."""
    return tokens((place or "").split(",")[0])
from .retrieval import BM25


class StoryEngine:
    def __init__(self, sources: list[Source]) -> None:
        self.sources = sources
        self.index = BM25().fit(sources)

    def compose(self, query: str, place: str | None = None, max_sentences: int = 5,
                mode: str = "grounded") -> dict:
        full_query = f"{query} {place or ''}".strip()
        hits = self.index.search(full_query, k=3)
        if not hits:
            return {
                "accepted": False,
                "reason": "No source in the library supports this place or topic.",
                "story": "", "sources": [], "grounding": None,
            }

        # If a place is given, require the top hit to match it (place-consistency gate).
        top_source, top_score = hits[0]
        if place and _city(place) and not (_city(place) & _city(top_source.place)):
            return {
                "accepted": False,
                "reason": f"The library has no grounded sources for '{place}'.",
                "story": "", "sources": [], "grounding": None,
            }

        # When a place is specified, keep only sources for that place so the story
        # stays coherent and on-place; topic-only queries may span sources.
        if place and _city(place):
            place_hits = [s for s, _ in hits if _city(place) & _city(s.place)]
            used_sources = place_hits or [top_source]
        else:
            used_sources = [s for s, _ in hits]
        if mode == "genai" and genai.available():
            gen = self._genai_story(full_query, top_source.place, used_sources)
            if gen is not None:
                return gen
        q_tokens = tokens(full_query)

        # Rank candidate sentences from the retrieved sources by query overlap,
        # keep source order stable for readability.
        scored: list[tuple[float, int, int, str]] = []
        for si, src in enumerate(used_sources):
            for sj, sent in enumerate(split_sentences(src.text)):
                overlap = len(tokens(sent) & q_tokens)
                scored.append((overlap, si, sj, sent))
        # pick the most relevant sentences, then restore a natural order
        scored.sort(key=lambda x: (-x[0], x[1], x[2]))
        chosen = scored[:max_sentences]
        chosen.sort(key=lambda x: (x[1], x[2]))
        body = " ".join(s for _, _, _, s in chosen)

        grounding = ground(body, used_sources, threshold=0.5)

        # Build renumbered citations in order of first use.
        order: list[int] = []
        cited_sentences = []
        for ann in grounding["sentences"]:
            si = ann["source_index"]
            if si is None:
                cited_sentences.append(ann["sentence"])
            else:
                if si not in order:
                    order.append(si)
                cited_sentences.append(f"{ann['sentence']} [{order.index(si) + 1}]")
        story = " ".join(cited_sentences)
        citations = [
            {"n": i + 1, "title": used_sources[si].title, "url": used_sources[si].url}
            for i, si in enumerate(order)
        ]
        return {
            "accepted": True,
            "place": top_source.place,
            "story": story,
            "grounding_score": grounding["grounding_score"],
            "unsupported": grounding["unsupported"],
            "citations": citations,
            "retrieved": [{"title": s.title, "score": sc} for s, sc in hits],
            "mode": "grounded",
        }

    def _genai_story(self, query: str, place: str, sources: list[Source]) -> dict | None:
        """Generate a narrative with an LLM, then VERIFY every sentence against
        the sources. Unsupported sentences are dropped, so accuracy is preserved."""
        facts = "\n".join(f"- {s.text}" for s in sources)
        system = (
            "You are a careful cultural guide. Write a short, vivid 4-6 sentence "
            "story about the place using ONLY the facts provided. Do not invent "
            "names, dates, or events that are not in the facts."
        )
        prompt = f"Place: {place}\nFocus: {query}\n\nFacts you may use:\n{facts}\n\nStory:"
        draft = genai.generate(prompt, system=system)
        if not draft:
            return None
        grounding = ground(draft, sources, threshold=0.5)
        # keep only supported sentences -> verified output
        order: list[int] = []
        kept = []
        for ann in grounding["sentences"]:
            si = ann["source_index"]
            if si is None:
                continue  # drop unsupported (hallucinated) sentence
            if si not in order:
                order.append(si)
            kept.append(f"{ann['sentence']} [{order.index(si) + 1}]")
        if not kept:
            return None
        verified = " ".join(kept)
        citations = [{"n": i + 1, "title": sources[si].title, "url": sources[si].url}
                     for i, si in enumerate(order)]
        n = len(grounding["sentences"]) or 1
        return {
            "accepted": True, "place": place, "story": verified,
            "grounding_score": round(len(kept) / n, 3),
            "unsupported": grounding["unsupported"],
            "citations": citations, "mode": "genai-verified",
            "dropped_unsupported": len(grounding["unsupported"]),
        }
