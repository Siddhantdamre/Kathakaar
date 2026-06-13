# Kathakaar v3 Architecture

## Design

Kathakaar separates four concerns:

1. Canonical knowledge: normalized records, media assets, provenance, rights,
   retrieval date, content hashes, and review status.
2. Retrieval: lexical TF-IDF/BM25 plus media embeddings, fused before place and
   topic checks.
3. Generation: extractive output by default, or a structured chat backend
   constrained to retrieved source IDs.
4. Validation: abstention, citation membership, claim support, rights auditing,
   and reproducible evaluation.

PostgreSQL is the optional canonical production store. Qdrant stores media
vectors and provenance payloads. The local JSONL and serialized retriever paths
remain first-class so tests and reviewers do not need external infrastructure.

## Multimodal Encoders

`HashingMultimodalEncoder` indexes captions, transcripts, creators, and media
metadata. It is deterministic and intended for CI.

`SiglipMultimodalEncoder` uses a pretrained shared image-text embedding model
for actual image retrieval. It loads lazily through the `multimodal` optional
dependency. The encoder can later be replaced with ColPali or ColQwen for
page-image retrieval without changing the knowledge or RAG contracts.

## Safety

- Place filtering happens before generation.
- Weak relevance or topic coverage produces `insufficient_evidence`.
- Every generated claim must cite a retrieved source.
- Citations outside the retrieved set reject the generation.
- Weakly supported claims reject the generation.
- Rights and attribution remain attached to media vectors and final sources.
