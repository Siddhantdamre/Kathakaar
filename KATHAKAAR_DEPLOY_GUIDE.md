# Kathakaar — full deployment guide (for someone who has never deployed)

You're shipping **two pieces** that talk to each other over the internet:

```
   [ web-app  (React UI) ]  --- calls /api/... --->  [ studio (FastAPI brain) ]
        hosted on Vercel                                  hosted on Render
```

Do them in this order: **backend first** (so you have its URL), then frontend.
Total time ~20 minutes. Everything below is free-tier.

---

## Before you start (once)
1. Push the project to GitHub (GitHub Desktop → Push). Make sure the
   `Kathakaar` repo on github.com contains both `studio/` and `web-app/`.
2. Create free accounts at **render.com** and **vercel.com**. Sign in to both
   with your GitHub so they can see your repos.

---

## PART A — Backend on Render (~8 min)

1. render.com → **New +** → **Web Service**.
2. **Connect** your GitHub and pick the **Kathakaar** repo.
3. Fill the form exactly:
   - **Name:** `kathakaar-api` (this becomes your URL)
   - **Root Directory:** `studio`        ← important, the app lives here
   - **Runtime/Language:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance type:** Free
4. Click **Create Web Service** and wait for "Live" (first build ~3–5 min).
5. Copy your backend URL from the top — e.g. `https://kathakaar-api.onrender.com`.
6. Test it: open `https://kathakaar-api.onrender.com/api/health` in a browser.
   You should see `{"status":"ok","sources":10}`. ✅ Backend done.

   > Free tier sleeps after ~15 min idle and wakes in ~30s on the next request.
   > Fine for a portfolio. CORS is already enabled, so the frontend can call it.

---

## PART B — Frontend on Vercel (~8 min)

1. vercel.com → **Add New… → Project** → import the **Kathakaar** repo.
2. In the configure screen:
   - **Root Directory:** click **Edit** → choose `web-app`   ← important
   - Framework Preset: **Vite** (auto-detected)
   - Build Command / Output: leave defaults (`npm run build` → `dist`)
3. Open **Environment Variables** and add ONE:
   - **Name:** `VITE_API_BASE`
   - **Value:** your Render URL from Part A, no trailing slash
     (e.g. `https://kathakaar-api.onrender.com`)
4. Click **Deploy**. Wait ~1–2 min for "Congratulations".
5. Open your live URL (e.g. `https://kathakaar.vercel.app`). ✅ Frontend done.

   > Why the env var? Vite bakes the backend URL into the build, so it must be
   > set **before** the build. If you change it later, click **Redeploy**.

---

## PART C — Verify the whole thing works (2 min)

On your live Vercel URL:
1. Pick **Konark India**, type **"carved wheels and chariot"**, Generate →
   you get a cited story and the grounding meter fills. ✅
2. Type **"alien spaceships and lasers"** → you get the **"Kathakaar declined to
   invent"** card. ✅  ← this is the money shot for recruiters.
3. (First request after idle may take ~30s while Render wakes — normal.)

If both work, you have a real, live, full-stack app. Put the Vercel URL on your
resume/LinkedIn and in the repo's "About" link.

---

## Troubleshooting
- **UI loads but every query says "Could not reach the API":** `VITE_API_BASE`
  is wrong/missing, or you didn't redeploy after setting it. Fix the value in
  Vercel → Settings → Environment Variables → **Redeploy**.
- **First request hangs ~30s:** Render free tier waking from sleep. Normal.
- **CORS error in the browser console:** already handled server-side
  (`allow_origins="*"`). To restrict it to your domain later, set the Render env
  var `KATHAKAAR_ALLOW_ORIGINS=https://your-app.vercel.app` and redeploy.
- **Render build fails on start command:** confirm **Root Directory = studio**
  (not the repo root). With root = studio the command is `uvicorn app.main:app …`.

## Local development
```bash
cd studio && pip install -r requirements.txt && uvicorn app.main:app --port 8000
# new terminal:
cd web-app && npm install && npm run dev      # http://localhost:5173
```

## Note on the "Cinematic" mode
Grounded and GenAI-verified modes are wired to the real backend. The
**Cinematic** tab is a clearly-labelled front-end concept (imaginative
reconstruction) — there is no video-generation backend behind it. Keep it as a
showcase or hide that tab; it never claims to be grounded.
