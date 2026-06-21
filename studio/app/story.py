"""Deterministic, fully-grounded story composer.

Every sentence in the output is selected from a retrieved source, so the story
is grounded by construction; the grounding layer then verifies and cites it.
No LLM, no API keys -> reproducible and deployable anywhere.
"""
from __future__ import annotations

import math
from collections import Counter

from . import genai
from .grounding import Source, ground, split_sentences, tokens
from .retrieval import BM25


def _city(place: str | None) -> set[str]:
    """Tokens of the city part only (text before the first comma)."""
    return tokens((place or "").split(",")[0])


def _stem(w: str) -> str:
    """Tiny deterministic stemmer so 'temple'/'temples' and
    'carve'/'carved'/'carving' compare equal in the relevance gate."""
    if w.endswith("s") and len(w) > 3:
        w = w[:-1]
    if w.endswith("ing") and len(w) > 5:
        w = w[:-3]
    elif w.endswith("ed") and len(w) > 4:
        w = w[:-2]
    return w


def _stems(toks: set[str]) -> set[str]:
    return {_stem(t) for t in toks}


# Generic "tell me about this place" intent words. They express intent, not a
# factual claim, so they are excluded when judging topical support.
_GENERIC = {_stem(w) for w in (
    "history", "culture", "story", "stories", "overview", "information",
    "significance", "facts", "general", "background", "about",
)}


class StoryEngine:
    def __init__(self, sources: list[Source]) -> None:
        self.sources = sources
        self.index = BM25().fit(sources)
        # Stemmed corpus vocabulary + document frequencies. A topic token whose
        # stem appears in NO source is treated as a request to invent (refused).
        self.vocab: set[str] = set()
        df: Counter[str] = Counter()
        for s in sources:
            st = _stems(tokens(s.text))
            self.vocab |= st
            for t in st:
                df[t] += 1
        # Low-signal stems (e.g. "world", "site", "heritage") appear in nearly
        # every source, so matching them does not prove topical relevance; ignore
        # stems occurring in >=80% of sources when scoring relevance.
        n = max(1, len(sources))
        cutoff = math.ceil(0.8 * n)
        self.common: set[str] = {t for t, c in df.items() if c >= cutoff}

    def compose(self, query: str, place: str | None = None, max_sentences: int = 5,
                mode: str = "grounded") -> dict:
        full_query = f"{query} {place or ''}".strip()
        hits = self.index.search(full_query, k=3)
        if not hits:
            return {
                "accepted": False,
                "reason": "No source in the library supports this place or topic.",
                "story": "", "grounding_score": 0.0, "relevance_score": 0.0,
                "unsupported": [], "citations": [], "retrieved": [],
                "mode": "grounded",
            }

        # Place gate: when a place is named, narrate ONLY from that place's sources.
        # If the place exists in the library, use it (and let the topic gate below
        # decide relevance) -- even if a different place out-ranked it on keywords.
        # Only refuse here when the place is absent from the library entirely.
        top_source, top_score = hits[0]
        if place and _city(place):
            place_hits = [s for s, _ in hits if _city(place) & _city(s.place)]
            if not place_hits:
                place_hits = [s for s in self.sources if _city(place) & _city(s.place)]
            if not place_hits:
                return {
                    "accepted": False,
                    "reason": f"The library has no grounded sources for '{place}'.",
                    "story": "", "grounding_score": 0.0, "relevance_score": 0.0,
                    "unsupported": [], "citations": [],
                    "retrieved": [{"title": s.title, "score": sc} for s, sc in hits],
                    "mode": "grounded",
                }
            used_sources = place_hits
            top_source = place_hits[0]
        else:
            used_sources = [s for s, _ in hits]

        # --- Topic-relevance gate -------------------------------------------------
        # The place gate above only proves we have sources FOR the place. This gate
        # proves the requested TOPIC is actually covered by those sources, instead
        # of silently returning generic place facts for an unsupported request.
        # Score only "informative" topic stems (drop the place name and
        # near-ubiquitous corpus words, which carry no topical signal).
        informative = (_stems(tokens(query)) - _stems(_city(place)) - _GENERIC) - self.common
        place_vocab: set[str] = set()
        for s in used_sources:
            place_vocab |= _stems(tokens(s.text))
        matched = informative & place_vocab
        if informative and not matched:
            if not (informative & self.vocab):
                reason = ("None of the requested topics appear in any source. "
                          "Kathakaar will not invent unsupported content.")
            else:
                reason = (f"No source for '{top_source.place}' covers "
                          f"'{query.strip()}'. Kathakaar only narrates what its "
                          "sources can prove.")
            return {
                "accepted": False, "reason": reason, "place": top_source.place,
                "story": "", "grounding_score": 0.0, "relevance_score": 0.0,
                "unsupported": [], "citations": [],
                "retrieved": [{"title": s.title, "score": sc} for s, sc in hits],
                "mode": "grounded",
            }
        relevance = round(len(matched) / len(informative), 3) if informative else 1.0
        # -------------------------------------------------------------------------

        if mode == "genai" and genai.available():
            gen = self._genai_story(full_query, top_source.place, used_sources)
            if gen is not None:
                gen["relevance_score"] = relevance
                return gen

        q_tokens = tokens(full_query)

        # Rank candidate sentences from the retrieved sources by query overlap,
        # keep source order stable for readability.
        scored = []
        for si, src in enumerate(used_sources):
            for sj, sent in enumerate(split_sentences(src.text)):
                overlap = len(tokens(sent) & q_tokens)
                scored.append((overlap, si, sj, sent))
        scored.sort(key=lambda x: (-x[0], x[1], x[2]))
        chosen = scored[:max_sentences]
        chosen.sort(key=lambda x: (x[1], x[2]))
        body = " ".join(s for _, _, _, s in chosen)

        grounding = ground(body, used_sources, threshold=0.5)

        order = []
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
            "relevance_score": relevance,
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
        order = []
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
