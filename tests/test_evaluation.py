from __future__ import annotations

from kathakaar.evaluation import (
    claim_support_score,
    compare_retrievers,
    evaluate,
    evaluate_robustness,
)
from kathakaar.retrieval import BM25Retriever, HybridRetriever, TfidfRetriever
from kathakaar.schemas import (
    BenchmarkQuery,
    GroundedClaim,
    SourceDocument,
)


def test_claim_support_is_exact_for_extractive_claim():
    source = SourceDocument(
        "s1",
        "Title",
        "Place",
        "https://example",
        "The stone chariot belongs to the temple complex.",
    )
    claim = GroundedClaim(
        "The stone chariot belongs to the temple complex.",
        ("s1",),
    )

    assert claim_support_score(claim, {"s1": source}) == 1.0


def test_end_to_end_metrics_are_reproducible():
    source = SourceDocument(
        "s1",
        "Stone Chariot",
        "Hampi",
        "https://example",
        "The stone chariot belongs to the temple complex.",
    )
    retriever = TfidfRetriever().fit([source])
    queries = [
        BenchmarkQuery(
            query_id="q1",
            query="Hampi stone chariot",
            place="Hampi",
            expected_source_ids=("s1",),
            theme="craft",
        )
    ]

    metrics = evaluate(retriever, queries)

    assert metrics.retrieval_recall_at_1 == 1.0
    assert metrics.citation_coverage == 1.0
    assert metrics.citation_precision == 1.0


def test_comparison_evaluates_multiple_retrievers():
    source = SourceDocument(
        "s1",
        "Stone Chariot",
        "Hampi",
        "https://example",
        "The stone chariot belongs to the temple complex.",
    )
    queries = [
        BenchmarkQuery(
            query_id="q1",
            query="Hampi stone chariot",
            place="Hampi",
            expected_source_ids=("s1",),
            theme="craft",
        )
    ]

    reports = compare_retrievers(
        {
            "tfidf": TfidfRetriever().fit([source]),
            "bm25": BM25Retriever().fit([source]),
        },
        queries,
    )

    assert reports["tfidf"].retrieval_recall_at_1 == 1.0
    assert reports["bm25"].retrieval_recall_at_1 == 1.0


def test_robustness_metrics_include_abstention():
    source = SourceDocument(
        "s1",
        "Stone Chariot",
        "Hampi",
        "https://example",
        "The stone chariot belongs to the temple complex.",
    )
    queries = [
        BenchmarkQuery(
            query_id="supported",
            query="stone chariot temple",
            place="Hampi",
            expected_source_ids=("s1",),
            theme="craft",
        ),
        BenchmarkQuery(
            query_id="unsupported",
            query="water engineering",
            place="Hampi",
            expected_source_ids=(),
            theme="water",
            should_abstain=True,
        ),
    ]

    metrics = evaluate_robustness(HybridRetriever().fit([source]), queries)

    assert metrics.accepted_query_accuracy == 1.0
    assert metrics.out_of_domain_rejection_rate == 1.0
