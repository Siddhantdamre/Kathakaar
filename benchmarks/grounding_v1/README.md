# Kathakaar Grounding Benchmark v1

The benchmark contains 12 cultural source documents and 12 held-out retrieval
queries. It measures:

- retrieval recall at 1 and 3
- mean reciprocal rank
- citation coverage
- citation precision using token-level source support
- mean claim support

The corpus is deliberately small and uses paraphrased source notes linked to
UNESCO pages. It is a reproducibility benchmark, not a comprehensive cultural
knowledge base.

```bash
python -m kathakaar fit-retriever
python -m kathakaar evaluate
python -m kathakaar compare-retrievers
```

Both TF-IDF and Okapi BM25 currently score 1.0 recall@1 on this deliberately
small, separable regression set. The comparison is infrastructure evidence,
not a claim that either sparse method is sufficient for open-domain cultural
retrieval.
