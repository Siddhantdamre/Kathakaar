# Grounding Benchmark v2

Version 2 adds same-place distractors, topic-place conflicts, unsupported
places, fabricated themes, provenance fields, and explicit abstention labels.
The added records are frozen summaries of official UNESCO World Heritage and
Intangible Cultural Heritage pages.

The benchmark measures accuracy only when the system accepts a query, coverage
on supported queries, place consistency, rejection of unsupported/conflicting
requests, and false acceptance. Cultural source summaries remain evaluation
fixtures; production use should refresh and review source material.

Rebuild with:

```bash
python scripts/build_grounding_v2.py
```
