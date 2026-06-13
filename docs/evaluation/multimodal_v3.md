# Multimodal Evaluation v3

The v3 fixture evaluates six supported queries and seven place-conflict or
out-of-domain requests over 28 normalized cultural records and 13 rights-aware
media assets.

| Metric | Score |
| --- | ---: |
| Positive-query coverage | 1.0000 |
| Accuracy when accepted | 1.0000 |
| Media evidence in top hit | 0.5000 |
| Place consistency | 1.0000 |
| Conflict/OOD rejection | 1.0000 |
| False acceptance | 0.0000 |

The checked-in result uses deterministic media metadata embeddings. It proves
the ingestion, fusion, provenance, abstention, and regression machinery. It
does not establish real visual-understanding accuracy. A separate GPU run with
SigLIP or a page-image retriever is required for that claim.

Declarative requests also pass through the transparent claim-consistency gate.
The gate closed the `mm-adv02` unsupported Antarctica claim while preserving
1.000 positive-query coverage. It is lexical consistency evidence, not a full
natural-language inference evaluation.

```bash
python scripts/build_knowledge_v3.py
python -m kathakaar kb-audit
python -m kathakaar fit-multimodal
python -m kathakaar validate-multimodal
```
