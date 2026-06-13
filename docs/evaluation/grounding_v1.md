# Grounding Benchmark v1

## Research Question

Can a compact cultural-storytelling pipeline retrieve the intended source and
produce factual claims that remain explicitly attributable to that source?

## Protocol

- Corpus: 12 paraphrased source notes
- Queries: 12 held-out natural-language retrieval queries
- Places: Hampi, Kyoto, Timbuktu, Machu Picchu, Agra, Mahabalipuram
- Retriever: fitted unigram TF-IDF with cosine similarity
- Generator: extractive sentence selection with structured source IDs

The query set is held out from fitting, while the source corpus is used to fit
inverse-document-frequency weights and document vectors.

## Metrics

| Metric | Score |
| --- | ---: |
| Recall@1 | 1.000 |
| Recall@3 | 1.000 |
| Mean reciprocal rank | 1.000 |
| Citation coverage | 1.000 |
| Citation precision | 1.000 |
| Mean token-level claim support | 1.000 |

## Reproduction

```bash
python -m kathakaar fit-retriever \
  --corpus benchmarks/grounding_v1/corpus.jsonl \
  --output artifacts/tfidf_v1.json

python -m kathakaar evaluate \
  --queries benchmarks/grounding_v1/queries.jsonl \
  --model artifacts/tfidf_v1.json \
  --output results/grounding_v1/evaluation.json
```

## Interpretation

The benchmark is intentionally small and the queries are well separated. A
perfect score therefore verifies deterministic retrieval and citation
plumbing, not open-domain cultural competence. The result is useful as a
regression checkpoint before introducing harder distractors, multilingual
queries, dense retrieval, or free-form language-model generation.
