"""Real cinematic video render hook — skeleton.

This is the integration point for true text-to-video (Google Veo, Runway, Luma)
plus voiceover (ElevenLabs) and stitching (ffmpeg). It is intentionally a
skeleton: with no provider key set it returns a clear "unavailable" job so the
UI degrades gracefully. When a key is present it queues a job; a production
deployment would run the per-scene generation in a background worker and store
the resulting media in object storage (S3/R2), then expose the URLs.
"""
from __future__ import annotations

import os
import time
import uuid

_JOBS: dict[str, dict] = {}


def provider() -> str | None:
    if os.environ.get("VEO_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "veo"
    if os.environ.get("RUNWAY_API_KEY"):
        return "runway"
    if os.environ.get("LUMA_API_KEY"):
        return "luma"
    return None


def available() -> bool:
    return provider() is not None


def start(manifest: dict) -> dict:
    job_id = uuid.uuid4().hex[:12]
    scenes = manifest.get("scenes", []) or []
    if not available():
        job = {
            "id": job_id, "status": "unavailable", "progress": 0,
            "scenes": len(scenes),
            "message": ("Real video rendering is not configured. Set VEO_API_KEY, "
                        "RUNWAY_API_KEY, or LUMA_API_KEY (and optionally "
                        "ELEVENLABS_API_KEY) on the server to enable. The free "
                        "in-browser cinematic still works without it."),
        }
        _JOBS[job_id] = job
        return job

    # --- INTEGRATION POINT (runs in a background worker in production) ---------
    # for i, scene in enumerate(scenes):
    #     clip = video_api.generate(prompt=f"{scene['visual_note']}. {scene['caption']}",
    #                               duration_ms=scene['duration_ms'], provider=provider())
    #     voice = tts.synthesize(scene['narration'])          # ElevenLabs MP3
    #     muxed = ffmpeg_mux(clip, voice)                     # video + narration
    #     url = storage.upload(muxed)                         # S3/R2 -> public URL
    #     job['clips'].append(url); job['progress'] = (i+1)/len(scenes)
    # final = ffmpeg_concat(job['clips']); job['video_url'] = storage.upload(final)
    job = {
        "id": job_id, "status": "queued", "provider": provider(),
        "progress": 0.0, "scenes": len(scenes), "created": time.time(),
        "message": "Queued. (Background worker not run in this skeleton.)",
    }
    _JOBS[job_id] = job
    return job


def status(job_id: str) -> dict:
    return _JOBS.get(job_id) or {"id": job_id, "status": "not_found"}
