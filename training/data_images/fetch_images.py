#!/usr/bin/env python3
"""Heritage-image dataset gatherer for the Kathakaar visual LoRA.

Pulls openly-licensed / public-domain images from museum + Commons open APIs and
writes a `manifest.csv` recording source, title, creator, license and URL for
EVERY file — so your dataset is fully attributable (this is the whole point).

No API keys required for the three sources below.

Usage:
    python fetch_images.py --subject "Konark Sun Temple" --out ./konark --per-source 20
    python fetch_images.py --subject "Mughal architecture" --out ./mughal --sources commons,met
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import urllib.parse
import urllib.request

UA = {"User-Agent": "KathakaarDataset/1.0 (educational portfolio; https://github.com/Siddhantdamre)",
      "Accept": "image/*,*/*"}


def _get(url: str, timeout: float = 30.0):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _download(url: str, dest: str) -> bool:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            f.write(r.read())
        return True
    except Exception as e:
        print("   ! download failed:", e)
        return False


# ── Source 1: Wikimedia Commons (CC / public domain) ────────────────────────
# NOTE: downloading raw upload.wikimedia.org URLs often returns HTTP 403 from
# cloud IPs (Kaggle/Colab) due to hotlink protection. We instead download via
# commons.wikimedia.org/Special:FilePath, the hotlink-safe redirect path.
def commons(subject: str, n: int):
    api = ("https://commons.wikimedia.org/w/api.php?action=query&format=json"
           "&generator=search&gsrnamespace=6&gsrlimit=%d&gsrsearch=%s"
           "&prop=imageinfo&iiprop=url|extmetadata") % (n, urllib.parse.quote(subject))
    data = _get(api)
    rows = []
    for page in data.get("query", {}).get("pages", {}).values():
        title = page.get("title", "")  # e.g. "File:Konark Sun Temple.jpg"
        if not title.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        fname = title.split(":", 1)[-1]
        # hotlink-safe, server-side scaled download URL (avoids 403):
        dl = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
              + urllib.parse.quote(fname) + "?width=1200")
        meta = (page.get("imageinfo") or [{}])[0].get("extmetadata", {})
        rows.append({
            "source": "wikimedia_commons", "url": dl, "title": title,
            "creator": (meta.get("Artist", {}) or {}).get("value", "")[:300],
            "license": (meta.get("LicenseShortName", {}) or {}).get("value", "unknown"),
        })
    return rows


# ── Source 2: The Metropolitan Museum (Open Access, public domain) ──────────
def met(subject: str, n: int):
    s = _get("https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q="
             + urllib.parse.quote(subject))
    ids = (s.get("objectIDs") or [])[: n * 3]
    rows = []
    for oid in ids:
        if len(rows) >= n:
            break
        try:
            o = _get(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}")
        except Exception:
            continue
        if o.get("isPublicDomain") and o.get("primaryImage"):
            rows.append({
                "source": "met_open_access", "url": o["primaryImage"],
                "title": o.get("title", ""), "creator": o.get("artistDisplayName", ""),
                "license": "Public Domain (CC0)",
            })
    return rows


# ── Source 3: Art Institute of Chicago (public-domain subset) ───────────────
def artic(subject: str, n: int):
    s = _get("https://api.artic.edu/api/v1/artworks/search?q=" + urllib.parse.quote(subject)
             + "&fields=id,title,image_id,artist_title,is_public_domain&limit=" + str(n * 2))
    rows = []
    for a in s.get("data", []):
        if len(rows) >= n:
            break
        if a.get("is_public_domain") and a.get("image_id"):
            url = f"https://www.artic.edu/iiif/2/{a['image_id']}/full/843,/0/default.jpg"
            rows.append({
                "source": "art_institute_chicago", "url": url,
                "title": a.get("title", ""), "creator": a.get("artist_title", ""),
                "license": "Public Domain (CC0)",
            })
    return rows


SOURCES = {"commons": commons, "met": met, "artic": artic}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    ap.add_argument("--out", default="./images")
    ap.add_argument("--per-source", type=int, default=20)
    ap.add_argument("--sources", default="commons,met,artic")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    manifest = os.path.join(args.out, "manifest.csv")
    seen = set()
    written = 0
    with open(manifest, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "source", "title", "creator", "license", "url"])
        w.writeheader()
        for name in [x.strip() for x in args.sources.split(",") if x.strip()]:
            fn = SOURCES.get(name)
            if not fn:
                print("unknown source:", name); continue
            print(f"\n== {name} : '{args.subject}' ==")
            try:
                rows = fn(args.subject, args.per_source)
            except Exception as e:
                print("  source error:", e); continue
            for r in rows:
                h = hashlib.md5(r["url"].encode()).hexdigest()[:10]
                if h in seen:
                    continue
                seen.add(h)
                ext = os.path.splitext(r["url"].split("?")[0])[1] or ".jpg"
                fname = f"{name}_{h}{ext}"
                if _download(r["url"], os.path.join(args.out, fname)):
                    w.writerow({"file": fname, **r})
                    written += 1
                    print(f"   + {fname}  [{r['license']}]")
    print(f"\nDone. {written} images + manifest.csv in {args.out}")
    print("NEXT: review images, delete off-topic ones, then point the LoRA notebook at this folder.")


if __name__ == "__main__":
    main()
