# Deploy Kathakaar — exact steps for THIS repo

Kathakaar's FastAPI app serves both the API **and** the web UI, so the simplest
real deployment is a single Render service. A static GitHub Pages copy is the
always-on fallback. Both are covered below.

> ⚠️ Start-command gotcha: the app lives at `studio/app/main.py`. The correct
> module path depends on Render's **Root Directory** setting:
> - Root Directory = `studio`  → start: `uvicorn app.main:app ...`  ✅ (this repo's render.yaml)
> - Root Directory = repo root → start: `uvicorn studio.app.main:app ...`
> Don't mix them — that mismatch is the #1 cause of a failed deploy here.

---

## Option A (recommended): one Render service = live UI + API

Everything works from one URL, no CORS needed.

1. Push the `cowork-upgrade` branch to GitHub (GitHub Desktop → Push origin).
2. render.com → **New → Web Service** → connect the `Kathakaar` repo.
3. Settings:
   - **Root Directory:** `studio`
   - **Environment:** Python (or Docker — a Dockerfile is included)
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - (these already match `studio/render.yaml` and `studio/Procfile`)
4. Create. When live, your URL is e.g. `https://kathakaar.onrender.com` — that
   page is the **full live app** (UI + grounded API + refusal gate).
   - Free tier sleeps when idle and cold-starts in ~30s — fine for a portfolio.
   - Optional GenAI mode: add env var `OPENAI_API_KEY` or `GEMINI_API_KEY`. Without
     it, the deterministic engine still works fully.

Put this Render URL on your resume/LinkedIn as the live demo.

---

## Option B: GitHub Pages (static demo) + Render (API)

Use this if you want a guaranteed-instant link (Pages never sleeps) that can also
talk to the live backend.

1. **Pages:** repo **Settings → Pages** → Source: *Deploy from a branch* →
   Branch `cowork-upgrade`, Folder `/docs` → Save. Live at
   `https://siddhantdamre.github.io/Kathakaar/`.
   - With no backend wired, it runs the built-in **demo mode** (real client-side
     refusal logic + sample data) — the "try breaking it" refusal works offline.
2. **Wire it to the live Render API (optional):** in `docs/index.html`, set the
   backend URL near the top of the script:
   ```js
   const API_BASE = (window.KATHAKAAR_API || "https://kathakaar.onrender.com").replace(/\/$/, "");
   ```
   CORS is already enabled server-side (`access-control-allow-origin: *`), so the
   Pages frontend can call Render directly. To lock it down, set the Render env
   var `KATHAKAAR_ALLOW_ORIGINS=https://siddhantdamre.github.io`.

---

## What's already done for you
- `requirements.txt`, `Procfile`, `render.yaml`, `Dockerfile`, `docker-compose.yml` — present and consistent (Root Directory = `studio`).
- **CORS** middleware added to `app/main.py` (env-overridable).
- Frontend **API_BASE** hook added to `docs/index.html` and `studio/web/index.html`.
- Verified locally: serves UI at `/`, `/api/health` ok, accept + refuse correct, CORS header emitted, 24 studio tests pass.

## Quick local smoke test
```bash
cd studio && pip install -r requirements.txt
uvicorn app.main:app --port 8000        # open http://localhost:8000
python scripts/eval_refusal.py          # 0.00 false-accept
```
