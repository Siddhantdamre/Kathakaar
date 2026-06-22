"""Real moving-video backgrounds via Pexels (free API key, key-gated).

Given a place/theme query, returns an MP4 URL of real cinematic footage to play
as the cinematic background. No key -> returns None, and the player falls back to
the Ken Burns image. This is REAL footage (not AI-generated); bespoke AI video
remains the optional Veo/Runway path in render.py.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


def available() -> bool:
    return bool(os.environ.get("PEXELS_API_KEY"))


def video_for(query: str) -> str | None:
    key = os.environ.get("PEXELS_API_KEY")
    if not key or not (query or "").strip():
        return None
    url = ("https://api.pexels.com/videos/search?per_page=1&orientation=landscape"
           "&size=medium&query=" + urllib.parse.quote(query.strip()))
    try:
        req = urllib.request.Request(url, headers={"Authorization": key})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.load(r)
        vids = d.get("videos", [])
        if not vids:
            return None
        files = [f for f in vids[0].get("video_files", [])
                 if f.get("file_type") == "video/mp4" and f.get("link")]
        if not files:
            return None
        files.sort(key=lambda f: abs((f.get("height") or 0) - 720))  # ~720p
        return files[0]["link"]
    except Exception:
        return None
