from __future__ import annotations

import warnings

from fastapi.testclient import TestClient

from app.main import app

warnings.filterwarnings("ignore")
client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["sources"] >= 10


def test_places_listed():
    places = client.get("/api/places").json()["places"]
    assert any("Hampi" in p for p in places)


def test_story_is_grounded_and_cited():
    r = client.post("/api/story", json={"query": "temple on the river", "place": "Hampi, India"})
    d = r.json()
    assert d["accepted"] is True
    assert d["grounding_score"] == 1.0
    assert len(d["citations"]) >= 1
    assert "[1]" in d["story"]


def test_story_stays_on_requested_place():
    d = client.post("/api/story", json={"query": "marble mausoleum", "place": "Agra, India"}).json()
    assert "Agra" in d["place"]
    assert "Taj Mahal" in d["story"]


def test_unknown_place_is_refused():
    d = client.post("/api/story", json={"query": "opera house", "place": "Sydney, Australia"}).json()
    assert d["accepted"] is False
    assert d["reason"]


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "Kathakaar" in r.text


def test_config_reports_genai():
    d = client.get("/api/config").json()
    assert "genai" in d and "provider" in d["genai"]


def test_genai_mode_falls_back_without_key():
    d = client.post("/api/story", json={"query": "temple river", "place": "Hampi, India", "mode": "genai"}).json()
    assert d["accepted"] is True  # falls back to deterministic grounding
    assert d["grounding_score"] == 1.0


def test_garbage_story_is_graceful():
    r = client.post("/api/story", json={"query": "", "place": "Nowhereville", "mode": "grounded"})
    assert r.status_code == 200
    assert client.post("/api/story", json={"query": "x"}).status_code in (200, 422)


def test_unsupported_place_refuses_not_crash():
    d = client.post("/api/story", json={"query": "history", "place": "Atlantis", "mode": "grounded"}).json()
    assert d["accepted"] is False and "reason" in d
