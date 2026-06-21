"""Cinematic manifest builder.

Turns a grounded story (place + theme) into a sequence of narrated SCENES,
styled by a world storytelling FORMAT and framed by a user-chosen timeline year.

This stays true to Kathakaar's thesis: the factual core of every scene is a
grounded sentence from cited sources (see `caption`); the storytelling form adds
*framing* (an opening invocation, connective phrasing, voice cadence) which is
clearly an interpretive retelling, not invented fact. No external APIs, no keys.
"""
from __future__ import annotations

import re

from .grounding import split_sentences
from .story import StoryEngine

# ── World storytelling forms ────────────────────────────────────────────────
# Each form changes the narration framing AND the synthesized-voice cadence
# (rate/pitch are passed to the browser SpeechSynthesis API on the frontend).
FORMATS: dict[str, dict] = {
    "oral": {
        "label": "Oral Tradition",
        "origin": "Global · Indigenous",
        "opening": "Gather close, and listen well.",
        "connector": "And so it came to pass that",
        "close": "And that is how the story is remembered.",
        "voice": {"rate": 0.93, "pitch": 1.0},
    },
    "griot": {
        "label": "Griot",
        "origin": "West Africa",
        "opening": "Hear now the griot, keeper of names and of years.",
        "connector": "Remember also that",
        "close": "The names are kept. The telling endures.",
        "voice": {"rate": 0.88, "pitch": 0.9},
    },
    "ballad": {
        "label": "Epic Ballad",
        "origin": "Europe · South Asia",
        "opening": "Sing, O memory, of stone and of kings.",
        "connector": "And still the song rises, for",
        "close": "So ends the verse, but not the glory.",
        "voice": {"rate": 0.85, "pitch": 1.05},
    },
    "koan": {
        "label": "Koan / Parable",
        "origin": "East Asia",
        "opening": "Consider one question, and let it open slowly.",
        "connector": "Now sit with this:",
        "close": "The question remains, and that is the answer.",
        "voice": {"rate": 0.8, "pitch": 1.0},
    },
    "myth": {
        "label": "Mythic Cycle",
        "origin": "Norse · Hellenic",
        "opening": "In an age the world has half-forgotten,",
        "connector": "Thus the fates decreed that",
        "close": "And the cycle turns, as all cycles must.",
        "voice": {"rate": 0.86, "pitch": 0.95},
    },
}

_SCENE_TITLES = ["The Opening", "The Turning", "The Height", "The Remembrance", "The Coda"]


def era_label(year: int) -> str:
    if year < 0:
        return f"{abs(year)} BCE · Antiquity"
    if year < 500:
        return f"{year} CE · Ancient"
    if year < 1500:
        return f"{year} CE · Medieval"
    if year < 1800:
        return f"{year} CE · Early Modern"
    if year < 1950:
        return f"{year} CE · Colonial Era"
    return f"{year} CE · Contemporary"


def _strip_citations(text: str) -> str:
    return re.sub(r"\s*\[\d+\]", "", text).strip()


def _chunk(items: list, n: int) -> list[list]:
    if n <= 0:
        return [items]
    size = max(1, (len(items) + n - 1) // n)
    return [items[i:i + size] for i in range(0, len(items), size)][:n] or [items]


def _lower_first(s: str) -> str:
    return (s[0].lower() + s[1:]) if s else s


def build_manifest(engine: StoryEngine, query: str, place: str | None,
                   year: int, fmt: str, total_secs: int = 60) -> dict:
    form = FORMATS.get(fmt, FORMATS["oral"])
    result = engine.compose(query or "history and architecture", place,
                            max_sentences=6, mode="grounded")
    if not result.get("accepted"):
        return {"accepted": False,
                "reason": result.get("reason", "No grounded sources for this request."),
                "place": result.get("place", place), "format": fmt,
                "format_label": form["label"]}

    sentences = [s for s in split_sentences(_strip_citations(result["story"])) if s]
    if not sentences:
        return {"accepted": False, "reason": "No narratable content.", "place": place}

    n = min(len(_SCENE_TITLES), max(2, min(4, len(sentences))))
    groups = _chunk(sentences, n)
    era = era_label(year)
    per_ms = max(4000, int(total_secs * 1000 / max(1, len(groups))))

    scenes = []
    for i, group in enumerate(groups):
        core = " ".join(group).strip()
        if i == 0:
            era_word = era.split('·')[-1].strip().lower()
            narration = f"{form['opening']} In {era_word} {result['place'].split(',')[0]}, {_lower_first(core)}"
        elif i == len(groups) - 1:
            narration = f"{form['connector']} {_lower_first(core)} {form['close']}"
        else:
            narration = f"{form['connector']} {_lower_first(core)}"
        scenes.append({
            "index": i,
            "title": _SCENE_TITLES[i],
            "narration": narration,
            "caption": core,                       # the grounded, factual line
            "duration_ms": per_ms,
            "visual_note": f"Slow cinematic move · {result['place']}",
        })

    return {
        "accepted": True,
        "title": f"{result['place'].split(',')[0]} — {form['label']}",
        "place": result["place"],
        "theme": query or "history and architecture",
        "era": era,
        "year": year,
        "format": fmt,
        "format_label": form["label"],
        "format_origin": form["origin"],
        "grounded": True,
        "voice": form["voice"],
        "citations": result.get("citations", []),
        "relevance_score": result.get("relevance_score"),
        "scenes": scenes,
    }
