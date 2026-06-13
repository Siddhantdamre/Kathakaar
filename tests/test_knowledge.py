from __future__ import annotations

import json

from kathakaar.knowledge import (
    IIIFManifestAdapter,
    KnowledgeBase,
    LibraryOfCongressAdapter,
)
from kathakaar.schemas import MediaAsset, SourceDocument


def test_knowledge_base_hashes_and_round_trips(tmp_path):
    document = SourceDocument(
        source_id="record",
        title="Stone Chariot",
        place="Hampi",
        url="https://example.test/record",
        text="A documented stone chariot.",
        publisher="Example Archive",
        license="CC BY 4.0",
        retrieved_at="2026-06-13",
        rights_status="open",
        attribution="Example Archive",
        media_assets=(
            MediaAsset(
                asset_id="image",
                media_type="image",
                url="https://example.test/image.jpg",
                caption="Stone chariot",
                rights_status="open",
                attribution="Example Archive",
            ),
        ),
    )
    knowledge = KnowledgeBase([document])
    path = knowledge.save(tmp_path / "kb.jsonl")

    restored = KnowledgeBase.load(path)
    audit = restored.audit()

    assert audit.valid is True
    assert audit.records == 1
    assert audit.media_assets == 1
    assert restored.documents[0].content_hash


def test_library_of_congress_parser_preserves_rights_and_media():
    payload = {
        "item": {
            "id": "http://www.loc.gov/item/123/",
            "title": "Historic Photograph",
            "description": ["A historic photograph."],
            "rights_information": "No known restrictions on publication.",
            "language": ["english"],
            "date": "1927",
        },
        "resources": [
            {
                "caption": "Photographic print",
                "files": [
                    [
                        {
                            "url": "https://tile.loc.gov/image.jpg",
                            "mimetype": "image/jpeg",
                            "size": 1000,
                        }
                    ]
                ],
            }
        ],
    }

    document = LibraryOfCongressAdapter("Agra").parse_item(payload)

    assert document.publisher == "Library of Congress"
    assert document.rights_status == "no_known_restrictions"
    assert document.media_assets[0].media_type == "image"


def test_iiif_manifest_adapter_parses_local_manifest(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "id": "https://example.test/manifest",
                "type": "Manifest",
                "label": {"en": ["Temple manuscript"]},
                "summary": {"en": ["A documented manuscript."]},
                "rights": "https://creativecommons.org/licenses/by/4.0/",
                "provider": [{"label": {"en": ["Example Museum"]}}],
                "metadata": [
                    {
                        "label": {"en": ["Place"]},
                        "value": {"en": ["Hampi"]},
                    }
                ],
                "items": [
                    {
                        "label": {"en": ["Page one"]},
                        "items": [
                            {
                                "items": [
                                    {
                                        "body": {
                                            "id": "https://example.test/page.jpg",
                                            "format": "image/jpeg",
                                        }
                                    }
                                ]
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    document = IIIFManifestAdapter(str(manifest)).fetch()[0]

    assert document.place == "Hampi"
    assert document.publisher == "Example Museum"
    assert document.media_assets[0].url == "https://example.test/page.jpg"
