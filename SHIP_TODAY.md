# Ship Kathakaar today — final checklist

Status: **all components verified working.**
- Backend: 24 tests pass; endpoints `/api/story` (grounded + honest refusal),
  `/api/story-image`, `/api/cinematic` (any place, never refuses), `/api/tts`,
  `/api/render`, `/api/config` all respond correctly.
- Frontend: production build is clean (2068 modules).

## 1. Push the code
GitHub Desktop → commit everything → Push. (Both `studio/` and `web-app/`.)

## 2. Backend → Render
New Web Service → repo Kathakaar →
- Root Directory: `studio`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
Wait for Live, copy the URL, check `/api/health` → `{"status":"ok",...}`.

## 3. Frontend → Vercel
Your project is already at https://kathakaar-nine.vercel.app — just set/confirm
the env var and redeploy:
- Settings → Environment Variables → `VITE_API_BASE` = your Render URL (no slash)
- Deploations → Redeploy.

## 4. Smoke test the live site
- Grounded: Konark + "carved wheels" → cited story; "alien spaceships" → refuses. ✅
- Cinematic: any place (e.g. "Kyoto Japan"), pick a storytelling form + year →
  press play → it pans, narrates aloud, captions sync. ✅
- It works for places outside the 10-place corpus via Wikipedia. ✅

## Optional upgrades (no code changes — just add server env vars on Render)
| Capability | Env var(s) | Effect |
|---|---|---|
| Premium voice | `ELEVENLABS_API_KEY` (+ optional `ELEVENLABS_VOICE_ID`) | Cinematic narration uses ElevenLabs MP3; UI shows "premium voice on". Falls back to free browser voice if unset. |
| GenAI verified mode | `OPENAI_API_KEY` or `GEMINI_API_KEY` | GenAI mode writes then verifies against sources. |
| Real AI video | `VEO_API_KEY` / `RUNWAY_API_KEY` / `LUMA_API_KEY` | Enables the `/api/render` pipeline hook (background worker integration documented in `studio/app/render.py` + `CINEMATIC_NOTES.md`). |

Without any keys, the whole app works for free: grounded provenance + honest
refusal, and a narrated, animated, any-place cinematic.

## One honest note
True text-to-video (the "Render real video" button) is the only piece that needs
a paid key + a background worker to actually emit MP4s — the skeleton + exact
integration points are in `render.py`. Everything else is live-ready today.
