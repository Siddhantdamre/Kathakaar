from __future__ import annotations

from kathakaar.retrieval import (
    BM25Retriever,
    HybridRetriever,
    TfidfRetriever,
    load_retriever,
)
from kathakaar.schemas import SourceDocument


def _documents() -> list[SourceDocument]:
    return [
        SourceDocument("temple", "Stone Temple", "Hampi", "https://example/1", "stone chariot"),
        SourceDocument("water", "Water Works", "Machu Picchu", "https://example/2", "channels"),
    ]


def test_retriever_ranks_relevant_document_first():
    retriever = TfidfRetriever().fit(_documents())

    hits = retriever.search("Hampi stone chariot", limit=2)

    assert hits[0].document.source_id == "temple"
    assert hits[0].score > hits[1].score


def test_retriever_artifact_round_trip(tmp_path):
    path = TfidfRetriever().fit(_documents()).save(tmp_path / "model.json")

    restored = TfidfRetriever.load(path)

    assert restored.search("water channels", limit=1)[0].document.source_id == "water"


def test_bm25_ranks_relevant_document_first():
    retriever = BM25Retriever().fit(_documents())

    hits = retriever.search("Hampi stone chariot", limit=2)

    assert hits[0].document.source_id == "temple"
    assert hits[0].score > hits[1].score


def test_bm25_artifact_round_trip_and_generic_loader(tmp_path):
    path = BM25Retriever().fit(_documents()).save(tmp_path / "bm25.json")

    restored = load_retriever(path)

    assert restored.search("water channels", limit=1)[0].document.source_id == "water"


def test_hybrid_retriever_rejects_topic_place_conflict():
    decision = (
        HybridRetriever()
        .fit(_documents())
        .assess(
            "water channels",
            place="Hampi",
        )
    )

    assert decision.accepted is False
    assert decision.hits == ()


def test_hybrid_retriever_round_trip(tmp_path):
    path = HybridRetriever().fit(_documents()).save(tmp_path / "hybrid.json")

    restored = load_retriever(path)

    assert isinstance(restored, HybridRetriever)
    decision = restored.assess("stone chariot", place="Hampi")
    assert decision.accepted is True
    assert decision.hits[0].document.source_id == "temple"


def test_hybrid_retriever_rejects_unsupported_declarative_claim():
    documents = [
        SourceDocument(
            "agra-taj",
            "Taj Mahal",
            "Agra, India",
            "https://example.test/taj",
            "Shah Jahan commissioned the white marble mausoleum for Mumtaz Mahal.",
        )
    ]

    decision = (
        HybridRetriever()
        .fit(documents)
        .assess(
            "the Taj Mahal marble was imported from Antarctica",
            place="Agra, India",
        )
    )

    assert decision.accepted is False
    assert decision.claim_gate_applied is True
    assert decision.claim_consistency_score < 0.7
    assert "antarctica" in decision.unsupported_claim_terms
    assert "import" in decision.unsupported_claim_terms


def test_hybrid_retriever_accepts_supported_declarative_claim():
    documents = [
        SourceDocument(
            "agra-taj",
            "Taj Mahal",
            "Agra, India",
            "https://example.test/taj",
            "Shah Jahan commissioned the white marble mausoleum for Mumtaz Mahal.",
        )
    ]

    decision = (
        HybridRetriever()
        .fit(documents)
        .assess(
            "The Taj Mahal was commissioned by Shah Jahan as a marble mausoleum.",
            place="Agra, India",
        )
    )

    assert decision.accepted is True
    assert decision.claim_gate_applied is True
    assert decision.claim_consistency_score == 1.0
    assert decision.unsupported_claim_terms == ()


def test_hybrid_retriever_rejects_high_overlap_false_noun():
    documents = [
        SourceDocument(
            "agra-taj",
            "Taj Mahal",
            "Agra, India",
            "https://example.test/taj",
            "Shah Jahan commissioned the white marble mausoleum for Mumtaz Mahal.",
        )
    ]

    decision = (
        HybridRetriever()
        .fit(documents)
        .assess(
            "The Taj Mahal was commissioned by Shah Jahan as a museum.",
            place="Agra, India",
        )
    )

    assert decision.accepted is False
    assert decision.claim_consistency_score > 0.7
    assert decision.unsupported_claim_terms == ("museum",)
