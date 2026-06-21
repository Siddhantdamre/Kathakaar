"""Global place data via Wikipedia's free REST API (no key required).

Lets Kathakaar narrate ANY place on Earth, grounded in a real, citable source,
with a real image. Network calls run server-side (no browser CORS). Designed to
fail soft: any error returns None so callers can fall back gracefully.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

_UA = "KathakaarBot/1.0 (portfolio project; cultural storytelling)"
_SEARCH = ("https://en.wikipedia.org/w/api.php?action=query&list=search"
           "&srsearch={}&format=json&srlimit=1")
_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"


def _get(url: str, timeout: float = 8.0) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def fetch_place(place: str | None) -> dict | None:
    """Resolve `place` to a Wikipedia article and return
    {title, extract, url, image} — or None if nothing usable is found."""
    if not place or not place.strip():
        return None
    title = place.strip()

    # 1) resolve the best matching article title via search
    s = _get(_SEARCH.format(urllib.parse.quote(place.strip())))
    if s:
        hits = s.get("query", {}).get("search", [])
        if hits:
            title = hits[0]["title"]

    # 2) fetch the page summary (extract + image)
    d = _get(_SUMMARY.format(urllib.parse.quote(title.replace(" ", "_"))))
    if not d:
        return None
    extract = (d.get("extract") or "").strip()
    if not extract:
        return None
    image = ((d.get("originalimage") or {}).get("source")
             or (d.get("thumbnail") or {}).get("source"))
    url = (((d.get("content_urls") or {}).get("desktop") or {}).get("page")
           or f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}")
    return {"title": d.get("title", title), "extract": extract,
            "url": url, "image": image}
