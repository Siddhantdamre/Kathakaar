# Kathakaar — Studio Web App (frontend)

The React/Vite UI for Kathakaar, wired to the FastAPI backend in `../studio`.
Grounded stories with citations, an honest grounding/relevance meter, photo
grounding, and the signature **refusal** state when sources don't support a request.

## Run locally (2 terminals)
```bash
# Terminal 1 — backend (from ../studio)
cd ../studio && pip install -r requirements.txt && uvicorn app.main:app --port 8000

# Terminal 2 — frontend (this folder)
npm install
npm run dev            # opens http://localhost:5173, auto-talks to localhost:8000
```

## Build for production
```bash
npm run build          # outputs ./dist  (static files)
npm run preview        # preview the production build locally
```

## Configuration
The frontend reads the backend URL from `VITE_API_BASE` (see `.env.example`).
Vite inlines env vars at **build time**, so set it in your host's build settings.
- unset + `npm run dev`  → uses `http://localhost:8000`
- unset + production build → same-origin (only works if one server serves both)
- set to your Render URL → frontend calls that backend

## Deploy
See `../KATHAKAAR_DEPLOY_GUIDE.md` for click-by-click instructions
(backend on Render, this frontend on Vercel).
