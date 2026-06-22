#!/usr/bin/env python3
"""Public-domain storytelling-text gatherer for the narration-style model.

Pulls full texts from Project Gutenberg (via the free Gutendex API) and from
Wikisource. These are the raw materials — anthologies of a tradition's tales,
epics, ballads, sagas — from which you'll hand-pick passages to build pairs.

Usage:
    python fetch_texts.py gutenberg --query "West African folk tales" --out ./griot --max 5
    python fetch_texts.py gutenberg --query "Norse sagas Edda" --out ./myth --max 5
    python fetch_texts.py wikisource --title "Child's Ballads" --out ./ballad
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request

UA = {"User-Agent": "KathakaarDataset/1.0 (educational portfolio)"}


def _get_json(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)


def _get_text(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def gutenberg(query, out, mx):
    os.makedirs(out, exist_ok=True)
    data = _get_json("https://gutendex.com/books/?search=" + urllib.parse.quote(query))
    books = (data.get("results") or [])[:mx]
    manifest = []
    for b in books:
        fmts = b.get("formats", {})
        txt_url = (fmts.get("text/plain; charset=utf-8")
                   or fmts.get("text/plain") or fmts.get("text/plain; charset=us-ascii"))
        if not txt_url:
            continue
        try:
            txt = _get_text(txt_url)
        except Exception as e:
            print("  skip", b.get("id"), e); continue
        title = re.sub(r"[^a-z0-9]+", "_", b.get("title", "book").lower())[:50]
        fn = f"gutenberg_{b['id']}_{title}.txt"
        open(os.path.join(out, fn), "w", encoding="utf-8").write(txt)
        authors = ", ".join(a.get("name", "") for a in b.get("authors", []))
        manifest.append({"file": fn, "id": b["id"], "title": b.get("title"),
                         "authors": authors, "license": "Public Domain (Project Gutenberg)",
                         "source_url": f"https://www.gutenberg.org/ebooks/{b['id']}"})
        print(f"  + {fn}  ({authors})")
    json.dump(manifest, open(os.path.join(out, "sources.json"), "w"), indent=2)
    print(f"\n{len(manifest)} texts + sources.json in {out}")
    print("NEXT: open the texts, pick authentic passages of the tradition, save each as a .txt, "
          "then run make_pairs.py on that folder.")


def wikisource(title, out):
    os.makedirs(out, exist_ok=True)
    api = ("https://en.wikisource.org/w/api.php?action=query&format=json&prop=extracts"
           "&explaintext=1&titles=" + urllib.parse.quote(title))
    data = _get_json(api)
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        text = page.get("extract", "")
        if not text:
            print("  no extract for", title); continue
        fn = "wikisource_" + re.sub(r"[^a-z0-9]+", "_", title.lower())[:50] + ".txt"
        open(os.path.join(out, fn), "w", encoding="utf-8").write(text)
        json.dump([{"file": fn, "title": title, "license": "see Wikisource page",
                    "source_url": "https://en.wikisource.org/wiki/" + urllib.parse.quote(title)}],
                  open(os.path.join(out, "sources.json"), "w"), indent=2)
        print(f"  + {fn}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gutenberg"); g.add_argument("--query", required=True)
    g.add_argument("--out", default="./texts"); g.add_argument("--max", type=int, default=5)
    w = sub.add_parser("wikisource"); w.add_argument("--title", required=True)
    w.add_argument("--out", default="./texts")
    a = ap.parse_args()
    if a.cmd == "gutenberg":
        gutenberg(a.query, a.out, a.max)
    else:
        wikisource(a.title, a.out)


if __name__ == "__main__":
    main()
