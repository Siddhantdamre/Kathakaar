from __future__ import annotations

from kathakaar.multimodal import HashingMultimodalEncoder, MultimodalRetriever
from kathakaar.schemas import MediaAsset, SourceDocument
from kathakaar.storage import qdrant_points


def test_qdrant_points_preserve_provenance_and_rights():
    document = SourceDocument(
        "record",
        "Stone Chariot",
        "Hampi",
        "https://example.test/record",
        "A documented monument.",
        content_hash="hash",
        media_assets=(
            MediaAsset(
                "image",
                "image",
                "https://example.test/image.jpg",
                caption="Stone chariot",
                license="CC BY 4.0",
                rights_status="open",
                attribution="Example Archive",
            ),
        ),
    )
    retriever = MultimodalRetriever(HashingMultimodalEncoder()).fit([document])

    point = qdrant_points(retriever)[0]

    assert point["payload"]["source_id"] == "record"
    assert point["payload"]["license"] == "CC BY 4.0"
    assert point["payload"]["attribution"] == "Example Archive"
