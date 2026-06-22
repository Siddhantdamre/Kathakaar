"""Cinematic manifest builder — works for ANY place, never hard-refuses.

Data sources, in order:
  1. Local grounded corpus (mode='cinematic' relaxes the strict topic gate).
  2. Wikipedia REST API (any place on Earth, with a real image) — see wiki.py.
  3. A clearly-labelled imaginative fallback, so the user always gets a film.

The factual core of each scene (`caption`) stays grounded + cited when sources
exist; the storytelling FORM adds framing, and the timeline YEAR sets the era
lens. Voice rate/pitch per form are sent to the browser SpeechSynthesis API.
"""
from __future__ import annotations

import re

from .grounding import split_sentences, tokens
from .story import StoryEngine, _city
from . import wiki, pexels

FORMATS: dict[str, dict] = {
    "oral": {"label": "Oral Tradition", "origin": "Global · Indigenous",
             "opening": "Gather close, and listen well.",
             "connector": "And so it came to pass that",
             "close": "And that is how the story is remembered.",
             "voice": {"rate": 1.0, "pitch": 1.0}},
    "griot": {"label": "Griot", "origin": "West Africa",
              "opening": "Hear now the griot, keeper of names and of years.",
              "connector": "Remember also that",
              "close": "The names are kept. The telling endures.",
              "voice": {"rate": 0.8, "pitch": 0.7}},
    "ballad": {"label": "Epic Ballad", "origin": "Europe · South Asia",
               "opening": "Sing, O memory, of stone and of kings.",
               "connector": "And still the song rises, for",
               "close": "So ends the verse, but not the glory.",
               "voice": {"rate": 1.1, "pitch": 1.25}},
    "koan": {"label": "Koan / Parable", "origin": "East Asia",
             "opening": "Consider one question, and let it open slowly.",
             "connector": "Now sit with this:",
             "close": "The question remains, and that is the answer.",
             "voice": {"rate": 0.72, "pitch": 1.05}},
    "myth": {"label": "Mythic Cycle", "origin": "Norse · Hellenic",
             "opening": "In an age the world has half-forgotten,",
             "connector": "Thus the fates decreed that",
             "close": "And the cycle turns, as all cycles must.",
             "voice": {"rate": 0.9, "pitch": 0.6}},
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


def _theme_filter(sentences: list[str], query: str) -> list[str]:
    q = tokens(query or "")
    if not q or len(sentences) <= 3:
        return sentences
    matched = [s for s in sentences if tokens(s) & q]
    return matched if len(matched) >= 2 else sentences


def build_manifest(engine: StoryEngine, query: str, place: str | None,
                   year: int, fmt: str, total_secs: int = 60, fetch_fn=None) -> dict:
    form = FORMATS.get(fmt, FORMATS["oral"])
    fetch_fn = fetch_fn or wiki.fetch_place
    citations: list[dict] = []
    image = None
    grounded = True
    place_label = (place or "").strip() or "a distant place"

    # 1) local grounded corpus — pull the place's sources DIRECTLY (no gate, so a
    #    known place like Konark always films regardless of the theme wording)
    sentences: list[str] = []
    pc = _city(place) if place else set()
    local_srcs = [s for s in engine.sources if pc and (pc & _city(s.place))]
    if local_srcs:
        text = " ".join(s.text for s in local_srcs)
        sentences = [x for x in split_sentences(text) if x]
        citations = [{"n": i + 1, "title": s.title, "url": s.url}
                     for i, s in enumerate(local_srcs)]
        place_label = local_srcs[0].place
    else:
        # 2) Wikipedia — any place on Earth, with a real image
        w = None
        try:
            w = fetch_fn(place)
        except Exception:
            w = None
        if w and w.get("extract"):
            sentences = [s for s in split_sentences(w["extract"]) if len(s.split()) >= 4][:10]
            citations = [{"n": 1, "title": f"{w['title']} — Wikipedia", "url": w["url"]}]
            image = w.get("image")
            place_label = w["title"]

    # Always resolve a real background image for the place (place-driven backdrop),
    # even when the narration text came from the local corpus.
    if image is None and place:
        try:
            w_img = fetch_fn(place)
            if w_img:
                image = w_img.get("image")
        except Exception:
            pass

    # Optional: real moving-video background (Pexels) keyed by place + theme.
    video_url = None
    if pexels.available():
        q = (f"{place or ''} {query or ''}").strip() or (place or "")
        try:
            video_url = pexels.video_for(q) or pexels.video_for(place or "")
        except Exception:
            video_url = None

    sentences = _theme_filter(sentences, query)

    # 3) never refuse — imaginative, clearly labelled
    if not sentences:
        grounded = False
        city = place_label.split(",")[0]
        sentences = [
            f"Let us imagine {city}.",
            "Though the written archive is silent here, the place endures in the mind's eye.",
            "Picture its light, its stone, and the people who crossed it across the years.",
            "This telling is imaginative, offered gently where the records do not reach.",
        ]

    n = min(len(_SCENE_TITLES), max(2, min(4, len(sentences))))
    groups = _chunk(sentences, n)
    era = era_label(year)
    era_word = era.split("·")[-1].strip().lower()
    per_ms = max(4000, int(total_secs * 1000 / max(1, len(groups))))

    scenes = []
    for i, group in enumerate(groups):
        core = " ".join(group).strip()
        if i == 0:
            narration = f"{form['opening']} In {era_word} {place_label.split(',')[0]}, {_lower_first(core)}"
        elif i == len(groups) - 1:
            narration = f"{form['connector']} {_lower_first(core)} {form['close']}"
        else:
            narration = f"{form['connector']} {_lower_first(core)}"
        scenes.append({
            "index": i, "title": _SCENE_TITLES[i], "narration": narration,
            "caption": core, "duration_ms": per_ms,
            "visual_note": f"Slow cinematic move · {place_label}",
        })

    return {
        "accepted": True,
        "title": f"{place_label.split(',')[0]} — {form['label']}",
        "place": place_label,
        "theme": query or "history",
        "era": era,
        "year": year,
        "format": fmt,
        "format_label": form["label"],
        "format_origin": form["origin"],
        "grounded": grounded,
        "image_url": image,
        "video_url": video_url,
        "voice": form["voice"],
        "citations": citations,
        "scenes": scenes,
    }
