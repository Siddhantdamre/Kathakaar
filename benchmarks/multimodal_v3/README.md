# Multimodal Benchmark v3

This benchmark tests retrieval over normalized cultural records plus curated,
rights-aware image assets. It includes six supported queries and four
topic-place or out-of-domain cases that must be rejected.

The official collection snapshot is frozen under
`knowledge/source_snapshots/` so the 28-record knowledge base can be rebuilt
offline and byte-for-byte reproducibly.

The default CI path uses deterministic caption/transcript embeddings so it can
run without a GPU. The same knowledge schema and retriever support a pretrained
SigLIP image-text encoder through the `multimodal` optional dependency.
