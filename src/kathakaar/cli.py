"""Command-line interface for fitted retrieval and grounded story evaluation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from kathakaar.evaluation import (
    compare_retrievers,
    evaluate,
    evaluate_multimodal,
    evaluate_robustness,
    format_comparison,
    format_metrics,
    format_multimodal,
    format_robustness,
    load_queries,
    write_comparison_report,
    write_multimodal_report,
    write_report,
    write_robustness_report,
)
from kathakaar.generation import GroundedStoryGenerator
from kathakaar.knowledge import (
    IIIFManifestAdapter,
    KnowledgeBase,
    LibraryOfCongressAdapter,
    SourceAdapter,
    WikimediaCommonsAdapter,
)
from kathakaar.multimodal import (
    HashingMultimodalEncoder,
    MultimodalRetriever,
    SiglipMultimodalEncoder,
    query_asset_from_path,
)
from kathakaar.rag import (
    ExtractiveStoryGenerator,
    GuardedMultimodalRAG,
    OllamaChatBackend,
    StructuredGenAIStoryGenerator,
)
from kathakaar.retrieval import (
    BM25Retriever,
    HybridRetriever,
    TfidfRetriever,
    load_corpus,
    load_retriever,
)
from kathakaar.storage import PostgresKnowledgeStore, QdrantMediaStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kathakaar")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fit_parser = subparsers.add_parser("fit-retriever")
    fit_parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("benchmarks/grounding_v1/corpus.jsonl"),
    )
    fit_parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/tfidf_v1.json"),
    )
    fit_parser.add_argument(
        "--method",
        choices=("tfidf", "bm25", "hybrid"),
        default="tfidf",
    )

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument(
        "--queries",
        type=Path,
        default=Path("benchmarks/grounding_v1/queries.jsonl"),
    )
    evaluate_parser.add_argument(
        "--model",
        type=Path,
        default=Path("artifacts/tfidf_v1.json"),
    )
    evaluate_parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/grounding_v1/evaluation.json"),
    )

    story_parser = subparsers.add_parser("story")
    story_parser.add_argument("query")
    story_parser.add_argument("--place", required=True)
    story_parser.add_argument("--theme", default="memory and heritage")
    story_parser.add_argument(
        "--model",
        type=Path,
        default=Path("artifacts/tfidf_v1.json"),
    )
    story_parser.add_argument("--limit", type=int, default=3)

    safe_story_parser = subparsers.add_parser(
        "safe-story",
        help="Generate only when topic, place, and source evidence are sufficient.",
    )
    safe_story_parser.add_argument("query")
    safe_story_parser.add_argument("--place", required=True)
    safe_story_parser.add_argument("--theme", default="memory and heritage")
    safe_story_parser.add_argument(
        "--model",
        type=Path,
        default=Path("artifacts/hybrid_v2.json"),
    )
    safe_story_parser.add_argument("--limit", type=int, default=3)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Measure selective accuracy, place consistency, and abstention.",
    )
    validate_parser.add_argument(
        "--queries",
        type=Path,
        default=Path("benchmarks/grounding_v2/queries.jsonl"),
    )
    validate_parser.add_argument(
        "--model",
        type=Path,
        default=Path("artifacts/hybrid_v2.json"),
    )
    validate_parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/grounding_v2/robustness.json"),
    )

    compare_parser = subparsers.add_parser("compare-retrievers")
    compare_parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("benchmarks/grounding_v1/corpus.jsonl"),
    )
    compare_parser.add_argument(
        "--queries",
        type=Path,
        default=Path("benchmarks/grounding_v1/queries.jsonl"),
    )
    compare_parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/grounding_v1/retriever_comparison.json"),
    )

    kb_build_parser = subparsers.add_parser(
        "kb-build",
        help="Normalize a JSONL corpus into the provenance-first knowledge schema.",
    )
    kb_build_parser.add_argument("input", type=Path)
    kb_build_parser.add_argument(
        "--output",
        type=Path,
        default=Path("knowledge/kathakaar_v3.jsonl"),
    )

    kb_audit_parser = subparsers.add_parser(
        "kb-audit",
        help="Validate provenance, rights, hashes, and media records.",
    )
    kb_audit_parser.add_argument(
        "--kb",
        type=Path,
        default=Path("knowledge/kathakaar_v3.jsonl"),
    )

    loc_parser = subparsers.add_parser(
        "ingest-loc",
        help="Add official Library of Congress records to a knowledge base.",
    )
    loc_parser.add_argument("query")
    loc_parser.add_argument("--format", default="photos")
    loc_parser.add_argument("--limit", type=int, default=5)
    _add_kb_output_args(loc_parser)

    commons_parser = subparsers.add_parser(
        "ingest-commons",
        help="Add rights-aware Wikimedia Commons media to a knowledge base.",
    )
    commons_parser.add_argument("query")
    commons_parser.add_argument("--place", required=True)
    commons_parser.add_argument("--limit", type=int, default=5)
    _add_kb_output_args(commons_parser)

    iiif_parser = subparsers.add_parser(
        "ingest-iiif",
        help="Add a IIIF Presentation 3 manifest to a knowledge base.",
    )
    iiif_parser.add_argument("manifest")
    _add_kb_output_args(iiif_parser)

    multimodal_fit_parser = subparsers.add_parser(
        "fit-multimodal",
        help="Fit text and media retrieval over the normalized knowledge base.",
    )
    multimodal_fit_parser.add_argument(
        "--kb",
        type=Path,
        default=Path("knowledge/kathakaar_v3.jsonl"),
    )
    multimodal_fit_parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/multimodal_v3.json"),
    )
    multimodal_fit_parser.add_argument(
        "--encoder",
        choices=("hashing", "siglip"),
        default="hashing",
    )
    multimodal_fit_parser.add_argument(
        "--siglip-model",
        default="google/siglip-base-patch16-224",
    )

    rag_parser = subparsers.add_parser(
        "rag-story",
        help="Run guarded multimodal retrieval and grounded story generation.",
    )
    rag_parser.add_argument("query")
    rag_parser.add_argument("--place", required=True)
    rag_parser.add_argument("--theme", default="memory and heritage")
    rag_parser.add_argument(
        "--model",
        type=Path,
        default=Path("artifacts/multimodal_v3.json"),
    )
    rag_parser.add_argument("--query-media", type=Path, default=None)
    rag_parser.add_argument(
        "--generator",
        choices=("extractive", "ollama"),
        default="extractive",
    )
    rag_parser.add_argument("--ollama-model", default="llama3.2")
    rag_parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
    )
    rag_parser.add_argument("--limit", type=int, default=4)

    multimodal_validate_parser = subparsers.add_parser(
        "validate-multimodal",
        help="Evaluate multimodal ranking, media evidence, and abstention.",
    )
    multimodal_validate_parser.add_argument(
        "--queries",
        type=Path,
        default=Path("benchmarks/multimodal_v3/queries.jsonl"),
    )
    multimodal_validate_parser.add_argument(
        "--model",
        type=Path,
        default=Path("artifacts/multimodal_v3.json"),
    )
    multimodal_validate_parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/multimodal_v3/evaluation.json"),
    )

    postgres_parser = subparsers.add_parser(
        "sync-postgres",
        help="Sync canonical knowledge records to PostgreSQL JSONB storage.",
    )
    postgres_parser.add_argument(
        "--kb",
        type=Path,
        default=Path("knowledge/kathakaar_v3.jsonl"),
    )
    postgres_parser.add_argument("--dsn-env", default="KATHAKAAR_DB_URL")

    qdrant_parser = subparsers.add_parser(
        "sync-qdrant",
        help="Sync fitted media vectors and provenance payloads to Qdrant.",
    )
    qdrant_parser.add_argument(
        "--model",
        type=Path,
        default=Path("artifacts/multimodal_v3.json"),
    )
    qdrant_parser.add_argument(
        "--url",
        default=os.getenv("QDRANT_URL", "http://localhost:6333"),
    )
    qdrant_parser.add_argument("--collection", default="kathakaar_media")
    qdrant_parser.add_argument("--api-key-env", default="QDRANT_API_KEY")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "fit-retriever":
        documents = load_corpus(args.corpus)
        fitted_retriever: BM25Retriever | HybridRetriever | TfidfRetriever
        if args.method == "bm25":
            fitted_retriever = BM25Retriever().fit(documents)
        elif args.method == "hybrid":
            fitted_retriever = HybridRetriever().fit(documents)
        else:
            fitted_retriever = TfidfRetriever().fit(documents)
        fitted_retriever.save(args.output)
        sys.stdout.write(
            f"Fitted {args.method.upper()} retriever on {len(documents)} sources: {args.output}\n"
        )
        return 0

    if args.command == "evaluate":
        loaded_retriever = load_retriever(args.model)
        grounding_metrics = evaluate(loaded_retriever, load_queries(args.queries))
        output_path = write_report(grounding_metrics, args.output)
        sys.stdout.write(f"{format_metrics(grounding_metrics)}\n\nSaved {output_path}\n")
        return 0

    if args.command == "story":
        loaded_retriever = load_retriever(args.model)
        hits = loaded_retriever.search(args.query, limit=args.limit)
        story = GroundedStoryGenerator().generate(
            place=args.place,
            theme=args.theme,
            hits=hits,
        )
        sys.stdout.write(json.dumps(story.to_dict(), indent=2))
        sys.stdout.write("\n")
        return 0

    if args.command == "safe-story":
        loaded_retriever = load_retriever(args.model)
        if not isinstance(loaded_retriever, HybridRetriever):
            raise ValueError("safe-story requires a hybrid retriever artifact")
        decision = loaded_retriever.assess(
            args.query,
            place=args.place,
            limit=args.limit,
        )
        if not decision.accepted:
            sys.stdout.write(
                json.dumps(
                    {
                        "status": "insufficient_evidence",
                        "retrieval": decision.to_dict(),
                    },
                    indent=2,
                )
            )
            sys.stdout.write("\n")
            return 2

        story = GroundedStoryGenerator().generate(
            place=args.place,
            theme=args.theme,
            hits=list(decision.hits),
        )
        sys.stdout.write(
            json.dumps(
                {
                    "status": "grounded",
                    "retrieval": decision.to_dict(),
                    "story": story.to_dict(),
                },
                indent=2,
            )
        )
        sys.stdout.write("\n")
        return 0

    if args.command == "validate":
        loaded_retriever = load_retriever(args.model)
        if not isinstance(loaded_retriever, HybridRetriever):
            raise ValueError("validate requires a hybrid retriever artifact")
        robustness_metrics = evaluate_robustness(
            loaded_retriever,
            load_queries(args.queries),
        )
        output_path = write_robustness_report(robustness_metrics, args.output)
        sys.stdout.write(f"{format_robustness(robustness_metrics)}\n\nSaved {output_path}\n")
        return 0

    if args.command == "compare-retrievers":
        documents = load_corpus(args.corpus)
        reports = compare_retrievers(
            {
                "bm25": BM25Retriever().fit(documents),
                "hybrid": HybridRetriever().fit(documents),
                "tfidf": TfidfRetriever().fit(documents),
            },
            load_queries(args.queries),
        )
        output_path = write_comparison_report(reports, args.output)
        sys.stdout.write(f"{format_comparison(reports)}\n\nSaved {output_path}\n")
        return 0

    if args.command == "kb-build":
        knowledge = KnowledgeBase()
        for document in load_corpus(args.input):
            knowledge.upsert(document)
        output_path = knowledge.save(args.output)
        audit = knowledge.audit()
        sys.stdout.write(
            json.dumps(
                {"output": str(output_path), "audit": audit.to_dict()},
                indent=2,
            )
        )
        sys.stdout.write("\n")
        return 0 if audit.valid else 2

    if args.command == "kb-audit":
        audit = KnowledgeBase.load(args.kb).audit()
        sys.stdout.write(json.dumps(audit.to_dict(), indent=2))
        sys.stdout.write("\n")
        return 0 if audit.valid else 2

    if args.command in {"ingest-loc", "ingest-commons", "ingest-iiif"}:
        knowledge = _load_or_create_knowledge(args.kb)
        adapter: SourceAdapter
        if args.command == "ingest-loc":
            adapter = LibraryOfCongressAdapter(
                query=args.query,
                resource_format=args.format,
                limit=args.limit,
            )
        elif args.command == "ingest-commons":
            adapter = WikimediaCommonsAdapter(
                query=args.query,
                place=args.place,
                limit=args.limit,
            )
        else:
            adapter = IIIFManifestAdapter(args.manifest)
        ingested = knowledge.ingest(adapter)
        output_path = knowledge.save(args.output)
        audit = knowledge.audit()
        sys.stdout.write(
            json.dumps(
                {
                    "ingested": ingested,
                    "output": str(output_path),
                    "audit": audit.to_dict(),
                },
                indent=2,
            )
        )
        sys.stdout.write("\n")
        return 0 if audit.valid else 2

    if args.command == "fit-multimodal":
        knowledge = KnowledgeBase.load(args.kb)
        encoder = (
            SiglipMultimodalEncoder(args.siglip_model)
            if args.encoder == "siglip"
            else HashingMultimodalEncoder()
        )
        retriever = MultimodalRetriever(encoder=encoder).fit(knowledge.documents)
        output_path = retriever.save(args.output)
        sys.stdout.write(
            f"Fitted {encoder.name} over {len(knowledge.documents)} records "
            f"and {len(retriever.asset_vectors)} media assets: {output_path}\n"
        )
        return 0

    if args.command == "rag-story":
        retriever = MultimodalRetriever.load(args.model)
        generator = (
            StructuredGenAIStoryGenerator(
                OllamaChatBackend(
                    model=args.ollama_model,
                    base_url=args.ollama_url,
                )
            )
            if args.generator == "ollama"
            else ExtractiveStoryGenerator()
        )
        query_asset = (
            query_asset_from_path(args.query_media) if args.query_media is not None else None
        )
        result = GuardedMultimodalRAG(retriever, generator).answer(
            query=args.query,
            place=args.place,
            theme=args.theme,
            limit=args.limit,
            query_asset=query_asset,
        )
        sys.stdout.write(json.dumps(result.to_dict(), indent=2))
        sys.stdout.write("\n")
        return 0 if result.status == "grounded" else 2

    if args.command == "validate-multimodal":
        retriever = MultimodalRetriever.load(args.model)
        metrics = evaluate_multimodal(retriever, load_queries(args.queries))
        output_path = write_multimodal_report(metrics, args.output)
        sys.stdout.write(f"{format_multimodal(metrics)}\n\nSaved {output_path}\n")
        return 0

    if args.command == "sync-postgres":
        dsn = os.getenv(args.dsn_env, "")
        if not dsn:
            raise ValueError(f"environment variable {args.dsn_env} is not set")
        knowledge = KnowledgeBase.load(args.kb)
        count = PostgresKnowledgeStore(dsn).sync(knowledge.documents)
        sys.stdout.write(f"Synced {count} canonical records to PostgreSQL.\n")
        return 0

    if args.command == "sync-qdrant":
        retriever = MultimodalRetriever.load(args.model)
        count = QdrantMediaStore(
            base_url=args.url,
            collection=args.collection,
            api_key=os.getenv(args.api_key_env, ""),
        ).sync(retriever)
        sys.stdout.write(f"Synced {count} media vectors to Qdrant collection {args.collection}.\n")
        return 0

    raise RuntimeError(f"unsupported command: {args.command}")


def _add_kb_output_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--kb",
        type=Path,
        default=Path("knowledge/kathakaar_v3.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("knowledge/kathakaar_v3.jsonl"),
    )


def _load_or_create_knowledge(path: Path) -> KnowledgeBase:
    return KnowledgeBase.load(path) if path.exists() else KnowledgeBase()


if __name__ == "__main__":
    raise SystemExit(main())
