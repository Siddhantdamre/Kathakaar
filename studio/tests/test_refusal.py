"""Tests for the topic-relevance refusal gate (the core honesty guarantee)."""
import json
from pathlib import Path

import pytest

from app.grounding import Source
from app.story import StoryEngine

BASE = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def engine() -> StoryEngine:
    src = []
    for line in (BASE / "data" / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            src.append(Source(d["source_id"], d["title"], d["url"], d["text"], d.get("place", "")))
    return StoryEngine(src)


# ---- should ACCEPT -----------------------------------------------------------
@pytest.mark.parametrize("query,place", [
    ("carved stone wheels chariot", "Konark, India"),
    ("marble mausoleum and gardens", "Agra, India"),
    ("temple carvings", "Khajuraho, India"),          # plural / stem match
    ("Nabataean sandstone treasury", "Petra, Jordan"),
    ("", "Konark, India"),                              # generic overview
    ("history", "Hampi, India"),                        # generic intent word
])
def test_supported_requests_are_accepted(engine, query, place):
    r = engine.compose(query, place)
    assert r["accepted"] is True
    assert r["story"]
    assert r["citations"]
    assert 0.0 <= r["relevance_score"] <= 1.0


# ---- should REFUSE: invention ------------------------------------------------
@pytest.mark.parametrize("query,place", [
    ("alien spaceships and lasers", "Konark, India"),
    ("dinosaurs and volcanoes", "Agra, India"),
    ("football world cup final", "Beijing, China"),     # 'world' alone must not pass
])
def test_invented_topics_are_refused(engine, query, place):
    r = engine.compose(query, place)
    assert r["accepted"] is False
    assert "invent" in r["reason"].lower()
    assert r["story"] == ""
    assert r["relevance_score"] == 0.0


# ---- should REFUSE: real topic, wrong place ----------------------------------
@pytest.mark.parametrize("query,place", [
    ("marble mausoleum", "Konark, India"),              # marble -> Agra
    ("great wall fortifications", "Agra, India"),        # wall -> Beijing
    ("Inca citadel", "Petra, Jordan"),                   # Inca -> Cusco
])
def test_wrong_place_topics_are_refused(engine, query, place):
    r = engine.compose(query, place)
    assert r["accepted"] is False
    assert "covers" in r["reason"].lower()


def test_grounding_and_relevance_are_distinct(engine):
    """A supported-but-partial topic should be fully grounded yet < 1.0 relevant."""
    r = engine.compose("temple architecture and carvings", "Konark, India")
    assert r["accepted"] is True
    assert r["grounding_score"] == 1.0          # sentences are source-backed
    assert r["relevance_score"] < 1.0           # but not every topic term is covered


def test_off_library_place_is_refused(engine):
    r = engine.compose("anything", "Atlantis")
    assert r["accepted"] is False
