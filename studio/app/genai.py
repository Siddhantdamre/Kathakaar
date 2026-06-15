"""Pluggable multimodal Generative AI client (text + vision) with safe fallback.

Provider is chosen from the environment so the app is deployable with no keys:

    LLM_PROVIDER = openai | gemini | ollama | none   (default: auto-detect)
    OPENAI_API_KEY=...        OPENAI_MODEL=gpt-4o-mini
    GEMINI_API_KEY=...        GEMINI_MODEL=gemini-1.5-flash
    OLLAMA_HOST=http://localhost:11434   OLLAMA_MODEL=llama3.2

If no provider is configured, ``available()`` is False and callers use their
deterministic engine. All calls go through httpx (no heavy SDK dependency).
Vision is supported by passing PNG/JPEG bytes; providers that lack vision fall
back to text-only.
"""
from __future__ import annotations

import base64
import os

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None  # type: ignore


def _provider() -> str:
    p = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if p:
        return p
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OLLAMA_HOST"):
        return "ollama"
    return "none"


def status() -> dict:
    p = _provider()
    return {
        "provider": p,
        "available": available(),
        "vision": p in {"openai", "gemini"},
        "model": _model(p),
    }


def _model(p: str) -> str | None:
    return {
        "openai": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "gemini": os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
        "ollama": os.environ.get("OLLAMA_MODEL", "llama3.2"),
    }.get(p)


def available() -> bool:
    if httpx is None:
        return False
    p = _provider()
    if p == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    if p == "gemini":
        return bool(os.environ.get("GEMINI_API_KEY"))
    if p == "ollama":
        return bool(os.environ.get("OLLAMA_HOST"))
    return False


def generate(prompt: str, *, system: str = "", image: bytes | None = None,
             timeout: float = 30.0) -> str | None:
    """Return generated text, or None if no provider is configured / on error."""
    if not available():
        return None
    p = _provider()
    try:
        if p == "openai":
            return _openai(prompt, system, image, timeout)
        if p == "gemini":
            return _gemini(prompt, system, image, timeout)
        if p == "ollama":
            return _ollama(prompt, system, timeout)
    except Exception:
        return None
    return None


def _openai(prompt: str, system: str, image: bytes | None, timeout: float) -> str:
    content: list[dict] = [{"type": "text", "text": prompt}]
    if image is not None:
        b64 = base64.b64encode(image).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}})
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": content})
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": _model("openai"), "messages": messages, "temperature": 0.4},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _gemini(prompt: str, system: str, image: bytes | None, timeout: float) -> str:
    parts: list[dict] = [{"text": (system + "\n\n" + prompt).strip()}]
    if image is not None:
        parts.append({"inline_data": {"mime_type": "image/png",
                                      "data": base64.b64encode(image).decode()}})
    model = _model("gemini")
    r = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": parts}]},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _ollama(prompt: str, system: str, timeout: float) -> str:
    host = os.environ["OLLAMA_HOST"].rstrip("/")
    r = httpx.post(
        f"{host}/api/generate",
        json={"model": _model("ollama"), "prompt": prompt, "system": system, "stream": False},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["response"].strip()


def ocr(image: bytes) -> str | None:
    """Best-effort local OCR (pytesseract). Returns None if unavailable."""
    try:
        import io

        import pytesseract
        from PIL import Image

        return pytesseract.image_to_string(Image.open(io.BytesIO(image))).strip() or None
    except Exception:
        return None
