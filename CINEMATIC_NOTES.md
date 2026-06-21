# Cinematic mode — what it is now, and the optional AI-video upgrade

## What it does (live today, free, no API keys)
Cinematic turns a **place + theme + timeline year + storytelling form** into a
narrated, animated mini-documentary:

- **Real motion** — a Ken Burns pan/zoom over place imagery plus a procedural
  canvas layer (drifting golden particles, a moving light sweep, vignette, film
  grain). If a background image fails to load, the procedural layer still carries
  the scene, so it never looks broken.
- **Real audio** — narration via the browser's built-in SpeechSynthesis (free,
  no key). Voice cadence (rate/pitch) changes per storytelling form. Best in
  Chrome/Edge; if unavailable, scenes auto-advance silently.
- **Synced captions** — each scene's grounded sentence animates in as it's spoken.
- **Free-form timeline slider** — any year from 1500 BCE to 2026 CE; the era
  frames the narration (it is used as a *lens*, never asserted as fact).
- **World storytelling forms** — Oral Tradition, Griot (West Africa), Epic
  Ballad, Koan/Parable (East Asia), Mythic Cycle (Norse/Hellenic). Each changes
  the opening invocation, connective phrasing, and voice.

It stays honest to Kathakaar's thesis: every scene's factual core is a grounded
sentence from cited sources (the form adds *framing*, clearly a retelling), and
the same refusal gate applies — ask for an unsupported theme and Cinematic
declines instead of inventing.

### Files
- Backend: `studio/app/cinematic.py` (manifest + storytelling forms),
  endpoint `POST /api/cinematic`, formats listed in `GET /api/config`.
- Frontend: `web-app/src/app/CinematicPlayer.tsx` (animation + narration),
  wired in `App.tsx`; client in `api.ts` (`postCinematic`, `getFormats`).

## The optional upgrade: true AI video (Veo / Runway / Luma)
Real text-to-video is a **paid, asynchronous** pipeline. The clean way to add it
later without changing the UI:

1. New endpoint `POST /api/render` takes the existing manifest and, per scene,
   calls a video API (Google Veo, Runway Gen-3, Luma) + a TTS API (ElevenLabs)
   using server-side keys; stores clips in object storage (S3/R2); returns job id.
2. `GET /api/render/{id}` reports progress + final media URLs.
3. Frontend swaps the canvas stage for a `<video>` once URLs arrive (the
   "Generating…" progress UI already exists).

This is a real-money, minutes-per-clip pipeline — wire it when you have keys and
a storage bucket. The current free version is what ships on Vercel + Render today.

---

## Update — any place on Earth, no refusals (Cinematic)

Cinematic no longer limits you to the 10-place corpus, and never hard-refuses.
Data resolution order in `studio/app/cinematic.py`:

1. **Local grounded corpus** (cinematic mode relaxes the strict topic gate, so a
   corpus place like Konark always films — this fixes the earlier
   "declined to film this" bug, which was the strict gate running on a short blurb).
2. **Wikipedia REST API** (`studio/app/wiki.py`, no API key) — resolves ANY place
   on Earth to a real, citable article + a real image (`image_url` on the manifest,
   used as the player's background).
3. **Imaginative fallback** — a clearly-labelled "Imaginative retelling" so the
   user always gets a film, even if Wikipedia has nothing.

Frontend: the Place field is now a free-text combobox (type any place; the 10
corpus places remain as suggestions), and Cinematic has its own **Theme** field
so the story follows the theme.

Note: **Grounded mode is unchanged** — it still refuses ungrounded requests (that
provenance guarantee is the portfolio centrepiece). Only **Cinematic** is
no-refusal, because its job is to always tell a story.

Verified: backend manifest logic tested for corpus / mocked-Wikipedia / fallback;
frontend builds clean (2068 modules). The live Wikipedia call runs server-side on
Render (this build sandbox blocks outbound Wikipedia, so it was validated with a
mock matching Wikipedia's documented REST shape).
