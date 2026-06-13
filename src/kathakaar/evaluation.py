"""Retrieval and citation-grounding evaluation for Kathakaar."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from kathakaar.generation import GroundedStoryGenerator
from kathakaar.multimodal import MultimodalRetriever
from kathakaar.retrieval import HybridRetriever, Retriever, tokenize
from kathakaar.schemas import BenchmarkQuery, GroundedClaim, SourceDocument
from kathakaar.statistics import Interval, wilson_interval


@dataclass(frozen=True)
class GroundingMetrics:
    retrieval_recall_at_1: float
    retrieval_recall_at_3: float
    mean_reciprocal_rank: float
    citation_coverage: float
    citation_precision: float
    mean_claim_support: float
    queries: int
    retrieval_recall_at_1_ci95: Interval = (0.0, 0.0)
    retrieval_recall_at_3_ci95: Interval = (0.0, 0.0)
    citation_precision_ci95: Interval = (0.0, 0.0)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = asdict(self)
        payload["retrieval_recall_at_1_ci95"] = list(self.retrieval_recall_at_1_ci95)
        payload["retrieval_recall_at_3_ci95"] = list(self.retrieval_recall_at_3_ci95)
        payload["citation_precision_ci95"] = list(self.citation_precision_ci95)
        return payload


@dataclass(frozen=True)
class RobustnessMetrics:
    positive_queries: int
    abstention_queries: int
    positive_coverage: float
    accepted_query_accuracy: float
    place_consistency: float
    out_of_domain_rejection_rate: float
    false_acceptance_rate: float
    accepted_query_accuracy_ci95: Interval = (0.0, 0.0)
    place_consistency_ci95: Interval = (0.0, 0.0)
    out_of_domain_rejection_ci95: Interval = (0.0, 0.0)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = asdict(self)
        payload["accepted_query_accuracy_ci95"] = list(self.accepted_query_accuracy_ci95)
        payload["place_consistency_ci95"] = list(self.place_consistency_ci95)
        payload["out_of_domain_rejection_ci95"] = list(self.out_of_domain_rejection_ci95)
        return payload


@dataclass(frozen=True)
class MultimodalMetrics:
    positive_queries: int
    abstention_queries: int
    positive_coverage: float
    accepted_query_accuracy: float
    media_evidence_rate: float
    place_consistency: float
    abstention_accuracy: float
    false_acceptance_rate: float
    accepted_query_accuracy_ci95: Interval = (0.0, 0.0)
    place_consistency_ci95: Interval = (0.0, 0.0)
    abstention_accuracy_ci95: Interval = (0.0, 0.0)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = asdict(self)
        payload["accepted_query_accuracy_ci95"] = list(self.accepted_query_accuracy_ci95)
        payload["place_consistency_ci95"] = list(self.place_consistency_ci95)
        payload["abstention_accuracy_ci95"] = list(self.abstention_accuracy_ci95)
        return payload


def load_queries(path: str | Path) -> list[BenchmarkQuery]:
    queries: list[BenchmarkQuery] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        queries.append(
            BenchmarkQuery(
                query_id=str(payload["id"]),
                query=str(payload["query"]),
                place=str(payload["place"]),
                expected_source_ids=tuple(payload["expected_source_ids"]),
                theme=str(payload["theme"]),
                should_abstain=bool(payload.get("should_abstain", False)),
            )
        )
    if not queries:
        raise ValueError("benchmark query set is empty")
    return queries


def evaluate(
    retriever: Retriever,
    queries: list[BenchmarkQuery],
    generator: GroundedStoryGenerator | None = None,
) -> GroundingMetrics:
    story_generator = generator or GroundedStoryGenerator()
    recall_at_1 = 0
    recall_at_3 = 0
    reciprocal_ranks: list[float] = []
    claims: list[GroundedClaim] = []
    source_lookup = {document.source_id: document for document in retriever.documents}

    for query in queries:
        hits = retriever.search(query.query, limit=3)
        ranked_ids = [hit.document.source_id for hit in hits]
        expected = set(query.expected_source_ids)
        recall_at_1 += int(bool(expected & set(ranked_ids[:1])))
        recall_at_3 += int(bool(expected & set(ranked_ids[:3])))
        rank = next(
            (index for index, source_id in enumerate(ranked_ids, start=1) if source_id in expected),
            None,
        )
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        story = story_generator.generate(
            place=query.place,
            theme=query.theme,
            hits=hits,
        )
        claims.extend(story.claims)

    covered = [claim for claim in claims if claim.source_ids]
    supported_scores = [claim_support_score(claim, source_lookup) for claim in covered]
    supported = [score for score in supported_scores if score >= 0.8]
    query_count = len(queries)
    return GroundingMetrics(
        retrieval_recall_at_1=round(recall_at_1 / query_count, 4),
        retrieval_recall_at_3=round(recall_at_3 / query_count, 4),
        mean_reciprocal_rank=round(sum(reciprocal_ranks) / query_count, 4),
        citation_coverage=round(len(covered) / len(claims), 4) if claims else 0.0,
        citation_precision=(round(len(supported) / len(covered), 4) if covered else 0.0),
        mean_claim_support=(
            round(sum(supported_scores) / len(supported_scores), 4) if supported_scores else 0.0
        ),
        queries=query_count,
        retrieval_recall_at_1_ci95=wilson_interval(recall_at_1, query_count),
        retrieval_recall_at_3_ci95=wilson_interval(recall_at_3, query_count),
        citation_precision_ci95=wilson_interval(len(supported), len(covered)),
    )


def evaluate_robustness(
    retriever: HybridRetriever,
    queries: list[BenchmarkQuery],
) -> RobustnessMetrics:
    positive = [query for query in queries if not query.should_abstain]
    abstention = [query for query in queries if query.should_abstain]
    accepted_positive = 0
    accepted_correct = 0
    place_consistent = 0
    rejected_abstention = 0

    for query in positive:
        decision = retriever.assess(query.query, place=query.place, limit=3)
        if not decision.accepted:
            continue
        accepted_positive += 1
        top_source = decision.hits[0].document.source_id
        accepted_correct += int(top_source in set(query.expected_source_ids))
        place_consistent += int(decision.place_consistent)

    for query in abstention:
        decision = retriever.assess(query.query, place=query.place, limit=3)
        rejected_abstention += int(not decision.accepted)

    return RobustnessMetrics(
        positive_queries=len(positive),
        abstention_queries=len(abstention),
        positive_coverage=round(_safe_divide(accepted_positive, len(positive)), 4),
        accepted_query_accuracy=round(
            _safe_divide(accepted_correct, accepted_positive),
            4,
        ),
        place_consistency=round(
            _safe_divide(place_consistent, accepted_positive),
            4,
        ),
        out_of_domain_rejection_rate=round(
            _safe_divide(rejected_abstention, len(abstention)),
            4,
        ),
        false_acceptance_rate=round(
            _safe_divide(len(abstention) - rejected_abstention, len(abstention)),
            4,
        ),
        accepted_query_accuracy_ci95=wilson_interval(accepted_correct, accepted_positive),
        place_consistency_ci95=wilson_interval(place_consistent, accepted_positive),
        out_of_domain_rejection_ci95=wilson_interval(rejected_abstention, len(abstention)),
    )


def evaluate_multimodal(
    retriever: MultimodalRetriever,
    queries: list[BenchmarkQuery],
) -> MultimodalMetrics:
    positive = [query for query in queries if not query.should_abstain]
    abstention = [query for query in queries if query.should_abstain]
    accepted_positive = 0
    accepted_correct = 0
    accepted_with_media = 0
    place_consistent = 0
    rejected_abstention = 0

    for query in positive:
        decision = retriever.assess(query.query, place=query.place, limit=3)
        if not decision.accepted:
            continue
        accepted_positive += 1
        accepted_correct += int(
            decision.hits[0].document.source_id in set(query.expected_source_ids)
        )
        accepted_with_media += int(bool(decision.hits[0].matched_asset_ids))
        place_consistent += int(decision.place_consistent)

    for query in abstention:
        rejected_abstention += int(
            not retriever.assess(query.query, place=query.place, limit=3).accepted
        )

    return MultimodalMetrics(
        positive_queries=len(positive),
        abstention_queries=len(abstention),
        positive_coverage=round(_safe_divide(accepted_positive, len(positive)), 4),
        accepted_query_accuracy=round(
            _safe_divide(accepted_correct, accepted_positive),
            4,
        ),
        media_evidence_rate=round(
            _safe_divide(accepted_with_media, accepted_positive),
            4,
        ),
        place_consistency=round(
            _safe_divide(place_consistent, accepted_positive),
            4,
        ),
        abstention_accuracy=round(
            _safe_divide(rejected_abstention, len(abstention)),
            4,
        ),
        false_acceptance_rate=round(
            _safe_divide(len(abstention) - rejected_abstention, len(abstention)),
            4,
        ),
        accepted_query_accuracy_ci95=wilson_interval(accepted_correct, accepted_positive),
        place_consistency_ci95=wilson_interval(place_consistent, accepted_positive),
        abstention_accuracy_ci95=wilson_interval(rejected_abstention, len(abstention)),
    )


def claim_support_score(
    claim: GroundedClaim,
    source_lookup: dict[str, SourceDocument],
) -> float:
    claim_tokens = set(tokenize(claim.text))
    if not claim_tokens:
        return 0.0
    source_tokens: set[str] = set()
    for source_id in claim.source_ids:
        source = source_lookup.get(source_id)
        if source:
            source_tokens.update(tokenize(source.text))
    return len(claim_tokens & source_tokens) / len(claim_tokens)


def write_report(metrics: GroundingMetrics, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "kathakaar-grounding-v1",
        "metrics": metrics.to_dict(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_robustness_report(
    metrics: RobustnessMetrics,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "benchmark": "kathakaar-grounding-v2",
                "metrics": metrics.to_dict(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def write_multimodal_report(
    metrics: MultimodalMetrics,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "benchmark": "kathakaar-multimodal-v3",
                "metrics": metrics.to_dict(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def compare_retrievers(
    retrievers: dict[str, Retriever],
    queries: list[BenchmarkQuery],
) -> dict[str, GroundingMetrics]:
    if not retrievers:
        raise ValueError("at least one retriever is required")
    return {name: evaluate(retriever, queries) for name, retriever in sorted(retrievers.items())}


def write_comparison_report(
    reports: dict[str, GroundingMetrics],
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": "kathakaar-grounding-v1",
        "retrievers": {name: metrics.to_dict() for name, metrics in reports.items()},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def format_metrics(metrics: GroundingMetrics) -> str:
    return "\n".join(
        [
            "| Metric | Score |",
            "| --- | ---: |",
            f"| Retrieval recall@1 | {metrics.retrieval_recall_at_1:.3f} |",
            f"| Retrieval recall@3 | {metrics.retrieval_recall_at_3:.3f} |",
            f"| Mean reciprocal rank | {metrics.mean_reciprocal_rank:.3f} |",
            f"| Citation coverage | {metrics.citation_coverage:.3f} |",
            f"| Citation precision | {metrics.citation_precision:.3f} |",
            f"| Mean claim support | {metrics.mean_claim_support:.3f} |",
        ]
    )


def format_robustness(metrics: RobustnessMetrics) -> str:
    return "\n".join(
        [
            "| Metric | Score |",
            "| --- | ---: |",
            f"| Positive-query coverage | {metrics.positive_coverage:.3f} |",
            f"| Accuracy when accepted | {metrics.accepted_query_accuracy:.3f} |",
            f"| Place consistency | {metrics.place_consistency:.3f} |",
            f"| OOD/conflict rejection | {metrics.out_of_domain_rejection_rate:.3f} "
            f"[{metrics.out_of_domain_rejection_ci95[0]:.2f}, "
            f"{metrics.out_of_domain_rejection_ci95[1]:.2f}] |",
            f"| False acceptance | {metrics.false_acceptance_rate:.3f} |",
        ]
    )


def format_multimodal(metrics: MultimodalMetrics) -> str:
    return "\n".join(
        [
            "| Metric | Score |",
            "| --- | ---: |",
            f"| Positive-query coverage | {metrics.positive_coverage:.3f} |",
            f"| Accuracy when accepted | {metrics.accepted_query_accuracy:.3f} |",
            f"| Media evidence in top hit | {metrics.media_evidence_rate:.3f} |",
            f"| Place consistency | {metrics.place_consistency:.3f} |",
            f"| Conflict/OOD rejection | {metrics.abstention_accuracy:.3f} "
            f"[{metrics.abstention_accuracy_ci95[0]:.2f}, "
            f"{metrics.abstention_accuracy_ci95[1]:.2f}] |",
            f"| False acceptance | {metrics.false_acceptance_rate:.3f} |",
        ]
    )


def format_comparison(reports: dict[str, GroundingMetrics]) -> str:
    lines = [
        "| Retriever | Recall@1 | Recall@3 | MRR | Citation precision |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, metrics in reports.items():
        lines.append(
            f"| {name} | {metrics.retrieval_recall_at_1:.3f} | "
            f"{metrics.retrieval_recall_at_3:.3f} | "
            f"{metrics.mean_reciprocal_rank:.3f} | "
            f"{metrics.citation_precision:.3f} |"
        )
    return "\n".join(lines)


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
