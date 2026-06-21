"""Kathakaar Studio API + static frontend (FastAPI)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import genai
from .grounding import Source
from .story import StoryEngine
from . import cinematic

BASE = Path(__file__).resolve().parent.parent
WEB = BASE / "web"


def load_sources(path: Path) -> list[Source]:
    out: list[Source] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        out.append(Source(d["source_id"], d["title"], d["url"], d["text"], d.get("place", "")))
    return out


SOURCES = load_sources(BASE / "data" / "corpus.jsonl")
ENGINE = StoryEngine(SOURCES)

app = FastAPI(title="Kathakaar Studio", version="2.0.0",
              description="Multimodal, source-grounded cultural storytelling.")

# Allow a separately-hosted frontend (e.g. GitHub Pages / Vercel) to call this
# API cross-origin. Reads are public and stateless, so "*" is appropriate; set
# KATHAKAAR_ALLOW_ORIGINS (comma-separated) to restrict to your own domains.
import os as _os
from fastapi.middleware.cors import CORSMiddleware as _CORS
_origins = [o.strip() for o in _os.environ.get("KATHAKAAR_ALLOW_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    _CORS, allow_origins=_origins, allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"],
)


class StoryRequest(BaseModel):
    query: str
    place: str | None = None
    mode: str = "grounded"  # "grounded" | "genai"


class CinematicRequest(BaseModel):
    query: str = ""
    place: str | None = None
    year: int = 1300
    format: str = "oral"
    duration_secs: int = 60


from fastapi import Request as _Request
from fastapi.responses import JSONResponse as _JSONResponse
from fastapi.exceptions import RequestValidationError as _RVE


@app.exception_handler(_RVE)
async def _validation_handler(request: _Request, exc: _RVE):
    return _JSONResponse(status_code=200, content={"accepted": False, "reason": "invalid request", "error": "invalid request"})


@app.exception_handler(Exception)
async def _unhandled_handler(request: _Request, exc: Exception):
    return _JSONResponse(status_code=200, content={"accepted": False, "reason": "internal error", "error": str(exc)[:200]})


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "sources": len(SOURCES)}


@app.get("/api/config")
def config() -> dict:
    return {
        "genai": genai.status(),
        "places": sorted({s.place for s in SOURCES}),
        "formats": [
            {"id": k, "label": v["label"], "origin": v["origin"]}
            for k, v in cinematic.FORMATS.items()
        ],
    }


@app.get("/api/places")
def places() -> dict:
    return {"places": sorted({s.place for s in SOURCES})}


@app.post("/api/story")
def story(req: StoryRequest) -> dict:
    return ENGINE.compose(req.query, req.place, mode=req.mode)


@app.post("/api/cinematic")
def cinematic_story(req: CinematicRequest) -> dict:
    """Build a narrated, scene-by-scene cinematic manifest from grounded sources."""
    return cinematic.build_manifest(
        ENGINE, req.query, req.place, req.year, req.format, req.duration_secs,
    )


@app.post("/api/story-image")
async def story_image(
    image: UploadFile = File(...),
    query: str = Form("history and architecture"),
    mode: str = Form("grounded"),
) -> dict:
    """Multimodal: identify the place from an uploaded photo, then ground a story."""
    data = await image.read()
    place_hint = None
    # 1) vision model identifies the place, if a vision provider is configured
    if genai.available() and genai.status()["vision"]:
        place_hint = genai.generate(
            "Name only the famous place or monument shown, as 'City, Country'. "
            "If unsure, reply 'unknown'.",
            system="You identify world heritage sites from photos.",
            image=data,
        )
    # 2) OCR fallback (any caption/text on the image)
    if not place_hint or place_hint.lower().strip() == "unknown":
        place_hint = genai.ocr(data) or place_hint
    if not place_hint:
        return {"accepted": False,
                "reason": "Could not identify a place from the image. Enable a vision "
                          "provider (set OPENAI_API_KEY/GEMINI_API_KEY) or type the place.",
                "mode": "image"}
    result = ENGINE.compose(query, place_hint.split("\n")[0].strip(), mode=mode)
    result["identified_place"] = place_hint.strip()
    return result


if WEB.exists():
    app.mount("/static", StaticFiles(directory=str(WEB)), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(WEB / "index.html"))
