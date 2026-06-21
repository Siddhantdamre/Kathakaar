"""Optional premium narration via ElevenLabs (server-side, key-gated).

If ELEVENLABS_API_KEY is set, `synthesize()` returns MP3 bytes; otherwise it
returns None and the frontend falls back to the browser's free SpeechSynthesis.
No key, no breakage.
"""
from __future__ import annotations

import json
import os
import urllib.request

_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
_DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs public "Rachel"


def available() -> bool:
    return bool(os.environ.get("ELEVENLABS_API_KEY"))


def synthesize(text: str, voice_id: str | None = None) -> bytes | None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key or not (text or "").strip():
        return None
    vid = voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or _DEFAULT_VOICE
    payload = json.dumps({
        "text": text[:2500],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.75, "style": 0.3},
    }).encode()
    req = urllib.request.Request(
        _URL.format(voice_id=vid), data=payload,
        headers={"xi-api-key": key, "Content-Type": "application/json",
                 "Accept": "audio/mpeg"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except Exception:
        return None
