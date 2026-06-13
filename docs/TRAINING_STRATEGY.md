# Training Strategy

## Current Decision

Do not train a large multimodal model from scratch. The project does not yet
have the volume, diversity, labels, compute, or cultural review needed to make
that scientifically defensible.

Use pretrained models and improve the system in this order:

1. Expand and audit the knowledge base.
2. Build hard retrieval and abstention evaluations.
3. Collect reviewed query, positive source, and hard-negative triples.
4. Fine-tune only the retriever or reranker with LoRA/contrastive learning.
5. Fine-tune generation style only after factuality and consent gates pass.

## Fine-Tuning Gate

Start retriever tuning after obtaining:

- at least 5,000 reviewed retrieval triples
- at least 20 places and 10 languages
- visual, textual, oral-history, and map examples
- same-place and same-topic hard negatives
- documented rights and consent for every training asset
- frozen train, validation, robustness, and community-review splits

Primary metrics:

- recall@1 and recall@5
- mean reciprocal rank
- place consistency
- media evidence rate
- out-of-domain rejection
- false acceptance
- performance by language, region, source institution, and modality

Generation training must additionally measure claim entailment, citation
correctness, unsupported-claim rate, cultural sensitivity, and reviewer
agreement.
