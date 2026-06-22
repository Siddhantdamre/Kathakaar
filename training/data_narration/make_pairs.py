#!/usr/bin/env python3
"""Turn authentic styled passages into (facts -> styled) training pairs.

You select short, authentic passages of a tradition (saved as .txt files), and
this builds rows for `narration_style_dataset.jsonl`:
    {style, style_label, facts, narration, source_file}
where `narration` is the authentic styled passage and `facts` is its neutral
content. This "reverse distillation" (styled -> facts) is the efficient way to
bootstrap the dataset.

Fact extraction:
  * If OPENAI_API_KEY is set, facts are auto-extracted by an LLM.
  * Otherwise a CSV stub is written for you to fill `facts` by hand, then convert.

Usage:
    # auto (needs OPENAI_API_KEY):
    python make_pairs.py build --dir ./griot_excerpts --style griot \
        --style-label "Griot (West Africa)" --out ../narration_style_dataset.jsonl
    # manual: writes pairs_to_fill.csv -> you fill 'facts' -> convert:
    python make_pairs.py tojsonl --csv pairs_to_fill.csv --out ../narration_style_dataset.jsonl
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import urllib.request


def extract_facts_llm(text: str) -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    prompt = ("Extract the neutral factual content of this passage as 1-3 plain, "
              "unembellished sentences. No style, no metaphor, just the facts:\n\n" + text[:3000])
    body = json.dumps({"model": model, "temperature": 0,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        return d["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("  ! LLM extract failed:", e)
        return None


def build(d, style, label, out):
    files = sorted(glob.glob(os.path.join(d, "*.txt")))
    if not files:
        print("no .txt passages in", d); return
    have_llm = bool(os.environ.get("OPENAI_API_KEY"))
    rows = []
    for fp in files:
        narration = open(fp, encoding="utf-8").read().strip()
        if not narration:
            continue
        facts = extract_facts_llm(narration) if have_llm else ""
        rows.append({"style": style, "style_label": label,
                     "facts": facts or "", "narration": narration,
                     "source_file": os.path.basename(fp)})
        print(f"  · {os.path.basename(fp)}  facts={'auto' if facts else 'BLANK (fill manually)'}")
    if have_llm:
        with open(out, "a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps({k: r[k] for k in ("style", "style_label", "facts", "narration")},
                                    ensure_ascii=False) + "\n")
        print(f"\nAppended {len(rows)} pairs to {out}")
    else:
        stub = os.path.join(d, "pairs_to_fill.csv")
        with open(stub, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["style", "style_label", "facts", "narration", "source_file"])
            w.writeheader(); w.writerows(rows)
        print(f"\nNo OPENAI_API_KEY -> wrote {stub}. Fill the 'facts' column, then run `tojsonl`.")


def tojsonl(csv_path, out):
    n = 0
    with open(csv_path, encoding="utf-8") as fh, open(out, "a", encoding="utf-8") as o:
        for row in csv.DictReader(fh):
            if not row.get("facts", "").strip():
                continue
            o.write(json.dumps({"style": row["style"], "style_label": row["style_label"],
                                "facts": row["facts"].strip(), "narration": row["narration"].strip()},
                               ensure_ascii=False) + "\n")
            n += 1
    print(f"Appended {n} completed pairs to {out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--dir", required=True); b.add_argument("--style", required=True)
    b.add_argument("--style-label", required=True); b.add_argument("--out", required=True)
    t = sub.add_parser("tojsonl")
    t.add_argument("--csv", required=True); t.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.dir, a.style, a.style_label, a.out)
    else:
        tojsonl(a.csv, a.out)


if __name__ == "__main__":
    main()
