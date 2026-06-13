# Adversarial robustness slice (v3) with confidence intervals

This slice adds near-domain adversarial embellishments: sentences that share
strong on-topic vocabulary with a real source but assert an unsupported claim,
such as "the Taj Mahal marble was imported from Antarctica." Every selective
metric includes a 95% Wilson confidence interval because the benchmark remains
small.

Commands:

```bash
PYTHONPATH=src python -m kathakaar validate \
  --queries benchmarks/grounding_v2/queries.jsonl \
  --model artifacts/hybrid_v2.json \
  --output results/grounding_v2/robustness.json

PYTHONPATH=src python -m kathakaar validate-multimodal \
  --queries benchmarks/multimodal_v3/queries.jsonl \
  --model artifacts/multimodal_v3.json \
  --output results/multimodal_v3/evaluation.json
```

## Results

Hybrid retrieval robustness (16 positive, 10 abstention):

| Metric | Score | 95% CI |
| --- | ---: | ---: |
| Positive-query coverage | 1.000 | - |
| Accuracy when accepted | 1.000 | [0.81, 1.00] |
| Place consistency | 1.000 | [0.81, 1.00] |
| **OOD/conflict rejection** | **1.000** | **[0.72, 1.00]** |

Multimodal (6 positive, 7 abstention): conflict/OOD rejection **1.000**
with a 95% CI of **[0.65, 1.00]**.

## Closed failure

The original lexical gate accepted `adv-02` and `mm-adv02` because "Taj Mahal"
and "marble" cleared the relevance and coverage thresholds. The new
claim-consistency gate:

- activates only for declarative factual inputs;
- compares claim terms against all selected, place-consistent evidence;
- requires full lexical support for declarative content terms;
- records the support score and unsupported terms in `RetrievalDecision`.

For the formerly leaked query, the production decision now rejects with support
`0.600000` and unsupported terms `import` and `antarctica`. Positive-query
coverage remains 1.000, so the fix did not reduce coverage on this fixture.

## Limits

The gate is a conservative lexical consistency check, not semantic entailment.
It intentionally requires full content-term support for declarative claims, so
paraphrases or aliases absent from the evidence may cause false abstentions.
Non-declarative requests still rely on the existing relevance, coverage, and
place checks. With only 10 and 7 abstention examples, the confidence intervals
remain wide; these results are regression evidence, not open-domain factuality.
