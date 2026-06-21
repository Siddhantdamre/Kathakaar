"""Honest refusal-gate evaluation for Kathakaar.

Measures whether the engine ACCEPTS supported requests and REFUSES unsupported
ones (invented topics, or real topics for the wrong place). Reports a confusion
matrix, refusal precision/recall, and the critical false-accept rate -- the rate
at which the system tells a story it cannot ground to the requested topic.

Run from the studio/ directory:  python scripts/eval_refusal.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.grounding import Source
from app.story import StoryEngine

BASE = Path(__file__).resolve().parent.parent


def load_sources() -> list[Source]:
    out = []
    for line in (BASE / "data" / "corpus.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            out.append(Source(d["source_id"], d["title"], d["url"], d["text"], d.get("place", "")))
    return out


def main() -> dict:
    engine = StoryEngine(load_sources())
    cases = [json.loads(l) for l in (BASE / "data" / "refusal_eval.jsonl")
             .read_text(encoding="utf-8").splitlines() if l.strip()]

    tp = fp = tn = fn = 0  # positive == "refuse"
    by_kind: dict[str, dict[str, int]] = {}
    rows = []
    for c in cases:
        r = engine.compose(c["query"], c["place"])
        actual = "refuse" if not r.get("accepted") else "accept"
        correct = actual == c["expect"]
        k = by_kind.setdefault(c["kind"], {"total": 0, "correct": 0})
        k["total"] += 1
        k["correct"] += int(correct)
        if c["expect"] == "refuse" and actual == "refuse":
            tp += 1
        elif c["expect"] == "accept" and actual == "refuse":
            fp += 1
        elif c["expect"] == "accept" and actual == "accept":
            tn += 1
        else:
            fn += 1
        rows.append({**c, "actual": actual, "correct": correct,
                     "relevance_score": r.get("relevance_score"),
                     "reason": r.get("reason")})

    n = len(cases)
    refuse_precision = tp / (tp + fp) if (tp + fp) else 0.0
    refuse_recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * refuse_precision * refuse_recall / (refuse_precision + refuse_recall)
          if (refuse_precision + refuse_recall) else 0.0)
    should_refuse = tp + fn
    false_accept_rate = fn / should_refuse if should_refuse else 0.0
    accuracy = (tp + tn) / n

    result = {
        "benchmark": "kathakaar-refusal-v1",
        "n_cases": n,
        "metrics": {
            "accuracy": round(accuracy, 3),
            "refusal_precision": round(refuse_precision, 3),
            "refusal_recall": round(refuse_recall, 3),
            "refusal_f1": round(f1, 3),
            "false_accept_rate": round(false_accept_rate, 3),
        },
        "confusion": {"refuse_correct": tp, "refuse_wrong": fp,
                      "accept_correct": tn, "accept_missed_refusal": fn},
        "by_kind": {k: {"accuracy": round(v["correct"] / v["total"], 3), **v}
                    for k, v in by_kind.items()},
    }
    print(json.dumps(result, indent=2))
    failures = [r for r in rows if not r["correct"]]
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  [{f['kind']}] expect={f['expect']} got={f['actual']} "
                  f"Q={f['query']!r} P={f['place']}")
    else:
        print("\nAll cases correct.")

    out_dir = BASE.parent / "results" / "refusal_v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "evaluation.json").write_text(json.dumps({**result, "rows": rows}, indent=2))
    return result


if __name__ == "__main__":
    main()
