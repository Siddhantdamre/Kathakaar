from __future__ import annotations

from kathakaar.multimodal import HashingMultimodalEncoder, MultimodalRetriever
from kathakaar.schemas import MediaAsset, SourceDocument


def _documents() -> list[SourceDocument]:
    return [
        SourceDocument(
            "hampi",
            "Vittala Temple",
            "Hampi",
            "https://example.test/hampi",
            "The temple complex belongs to the Vijayanagara period.",
            media_assets=(
                MediaAsset(
                    "hampi-image",
                    "image",
                    "https://example.test/hampi.jpg",
                    caption="Stone chariot at the Vittala temple",
                ),
            ),
        ),
        SourceDocument(
            "agra",
            "Agra Fort",
            "Agra",
            "https://example.test/agra",
            "A Mughal fortified palace complex.",
            media_assets=(
                MediaAsset(
                    "agra-image",
                    "image",
                    "https://example.test/agra.jpg",
                    caption="Red sandstone walls of Agra Fort",
                ),
            ),
        ),
    ]


def test_multimodal_retriever_uses_media_caption_signal():
    retriever = MultimodalRetriever(HashingMultimodalEncoder()).fit(_documents())

    decision = retriever.assess("stone chariot", place="Hampi")

    assert decision.accepted is True
    assert decision.hits[0].document.source_id == "hampi"
    assert decision.hits[0].matched_asset_ids == ("hampi-image",)


def test_multimodal_retriever_rejects_place_topic_conflict():
    retriever = MultimodalRetriever(HashingMultimodalEncoder()).fit(_documents())

    decision = retriever.assess("red sandstone fort", place="Hampi")

    assert decision.accepted is False


def test_multimodal_artifact_round_trip(tmp_path):
    path = (
        MultimodalRetriever(HashingMultimodalEncoder())
        .fit(_documents())
        .save(tmp_path / "model.json")
    )

    restored = MultimodalRetriever.load(path)

    assert restored.search("stone chariot", place="Hampi")[0].document.source_id == "hampi"


def test_multimodal_retriever_rejects_unsupported_declarative_claim():
    documents = [
        SourceDocument(
            "agra-taj",
            "Taj Mahal",
            "Agra, India",
            "https://example.test/taj",
            "The white marble mausoleum was commissioned by Shah Jahan.",
            media_assets=(
                MediaAsset(
                    "taj-image",
                    "image",
                    "https://example.test/taj.jpg",
                    caption="Historic photograph of the Taj Mahal marble mausoleum",
                ),
            ),
        )
    ]
    retriever = MultimodalRetriever(HashingMultimodalEncoder()).fit(documents)

    decision = retriever.assess(
        "the marble was imported from Antarctica",
        place="Agra, India",
    )

    assert decision.accepted is False
    assert decision.claim_gate_applied is True
    assert "antarctica" in decision.unsupported_claim_terms
