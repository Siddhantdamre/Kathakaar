# Refusal-gate evaluation (refusal_v1)

**Claim under test:** Kathakaar "only tells you what its sources can prove" and
"refuses rather than inventing." This evaluation checks whether that claim
actually holds at the engine level.

## The bug this fixes

Before this change, the composer only gated on **place**. A request for a real
place but an unsupported **topic** (e.g. *"alien spaceships"* for the Konark Sun
Temple) was accepted: the engine retrieved Konark, copied Konark's own sentences,
and — because the story is assembled *from* the source — scored them as 100%
"grounded." The grounding score was therefore vacuous: it could never fail.

## What changed

A **topic-relevance gate** now runs after the place gate. It compares the
*informative* tokens of the request (dropping the place name, a small set of
generic-intent words such as "history/overview", and near-ubiquitous corpus
words such as "world/heritage/site") against the vocabulary of the place's
sources, using a light deterministic stemmer so "temple"/"temples" and
"carve"/"carved"/"carving" match.

- If no informative topic token is supported **and** none appear anywhere in the
  corpus → refuse as **invention** ("will not invent unsupported content").
- If they appear elsewhere but not for this place → refuse as **wrong place**
  ("no source for X covers Y").
- Otherwise accept, and report an honest `relevance_score` = fraction of
  informative topic tokens actually supported (distinct from `grounding_score`).

## Dataset

`studio/data/refusal_eval.jsonl` — 29 hand-built cases across all 10 corpus
sites, in four categories: `on_topic` (14), `generic` (3), `invention` (6),
`wrong_place` (6). This is a **designed diagnostic set**, not a held-out
benchmark; its purpose is to pin behavior and guard against regressions.

## Results

Run: `cd studio && python scripts/eval_refusal.py`

| Metric | Value |
|---|---|
| Accuracy | 1.00 (29/29) |
| Refusal precision | 1.00 |
| Refusal recall | 1.00 |
| **False-accept rate** (ungrounded request told as a story) | **0.00** |

Per category: on_topic 14/14, generic 3/3, invention 6/6, wrong_place 6/6.

## Honest limitations

- The gate is **lexical**, not semantic. With no LLM/embeddings (a deliberate
  zero-dependency, reproducible design choice), it cannot bridge true synonyms —
  e.g. a query for "carvings" is supported by a source that says "sculpture"
  only if a shared stem exists. Recall on paraphrased topics is therefore lower
  than a semantic retriever would achieve.
- Perfect scores reflect a **small, designed** set, not a claim of general
  accuracy. The value is a guaranteed-zero false-accept rate on these cases and
  a regression guard, not a leaderboard number.
- The stemmer is intentionally tiny (plural + `-ing`/`-ed`); it is not a full
  morphological analyzer.
