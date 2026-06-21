# Kathakaar Studio


> **The problem.** Source-grounded writing needs a guarantee that every sentence is backed by a real source; this app makes that grounding visible and refuses to narrate what it can't cite. See `../PROBLEM_BRIEFS/Kathakaar_problem.md`.

**Source-grounded cultural storytelling — as a deployable web app.**

Type a place and a theme; the app retrieves real source passages, composes a
short story **only from sentences a source supports**, shows inline `[n]`
citations and a grounding score, and **refuses** to narrate places or claims it
can't ground. Fully deterministic — no LLM, no API keys, no GPU — so it runs and
deploys anywhere for free.

![architecture](docs/architecture.txt)

## What's inside

| Layer | Tech | File |
|---|---|---|
| Frontend | single-file HTML/CSS/JS (no build step) | `web/index.html` |
| Backend API | FastAPI | `app/main.py` |
| Retrieval | BM25 over a cultural corpus | `app/retrieval.py` |
| Grounding + citations | lexical support + citation renumbering | `app/grounding.py` |
| Story composer | deterministic, extractive, grounded-by-construction | `app/story.py` |
| Data | 10 UNESCO-site source records | `data/corpus.jsonl` |

API:
- `GET /api/health` — liveness + source count
- `GET /api/places` — places the library can ground
- `POST /api/story` — `{ "query": "...", "place": "..."? }` → grounded story + citations + score

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# open http://localhost:8000
```

Or with Docker:

```bash
docker compose up --build       # http://localhost:8000
```

## Test

```bash
pip install pytest httpx
pytest -q
```

## Deploy (one click)

- **Render**: repo includes `render.yaml` — New → Blueprint → pick the repo.
- **Railway / Heroku-style**: `Procfile` is included.
- **Docker host (Fly.io, Cloud Run, a VM)**: `Dockerfile` is included; the
  container reads `$PORT`.

## How grounding works

Each output sentence is matched to its best source by content-word overlap; a
sentence is only kept (and cited) if overlap clears a threshold, otherwise it is
flagged as unsupported. The **grounding score** is the fraction of sentences a
source supports. Place-specific requests are constrained to that place's sources,
and places/claims with no support are refused — the safety property that makes
the output trustworthy.

## License

MIT

## Multimodal Generative AI (optional)

The app runs deterministically with no keys. To enable GenAI + vision, set env vars:

```bash
# pick ONE provider
export OPENAI_API_KEY=sk-...        # OPENAI_MODEL=gpt-4o-mini (vision-capable)
# or
export GEMINI_API_KEY=...           # GEMINI_MODEL=gemini-1.5-flash (vision-capable)
# or a local model
export OLLAMA_HOST=http://localhost:11434   # OLLAMA_MODEL=llama3.2 (text only)
```

- **Text GenAI**: the model drafts; the deterministic layer then **verifies** the
  output (Kathakaar strips unsupported sentences; Cons.trukt keeps the rule-based
  risk level — the model only explains). Accuracy is preserved either way.
- **Vision**: drop an image in the UI. With a vision provider it's read directly;
  otherwise local OCR (`pip install pytesseract pillow`) is used. With neither, the
  app says so instead of guessing.
- `GET /api/config` reports the active provider so the UI shows it live.
