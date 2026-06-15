"""Grounding + citation layer (deterministic, standard library only)."""
from __future__ import annotations

import re
from dataclasses import dataclass

_STOP = {
    "the","a","an","and","or","but","of","to","in","on","at","for","is","are","was",
    "were","be","been","as","by","with","that","this","it","its","from","into","over",
    "near","they","their","has","have","had","which","who","whom","where","when","while",
    "also","than","what","tell","me","about","story","place",
}


@dataclass
class Source:
    source_id: str
    title: str
    url: str
    text: str
    place: str = ""


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in _STOP and len(w) > 2}


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def support(sentence: str, source: Source) -> float:
    s, d = tokens(sentence), tokens(source.text)
    if not s or not d:
        return 0.0
    return len(s & d) / len(s)


def ground(text: str, sources: list[Source], threshold: float = 0.5) -> dict:
    annotated = []
    for sentence in split_sentences(text):
        best_i, best = None, 0.0
        for i, src in enumerate(sources):
            sc = support(sentence, src)
            if sc > best:
                best_i, best = i, sc
        ok = best >= threshold
        annotated.append(
            {"sentence": sentence, "source_index": best_i if ok else None,
             "score": round(best, 3), "supported": ok}
        )
    n = len(annotated)
    supported = [a for a in annotated if a["supported"]]
    return {
        "sentences": annotated,
        "grounding_score": round(len(supported) / n, 3) if n else 0.0,
        "unsupported": [a["sentence"] for a in annotated if not a["supported"]],
    }
