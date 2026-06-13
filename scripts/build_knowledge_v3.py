"""Build the normalized v3 knowledge base with curated open-media records."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from kathakaar.knowledge import (
    JsonlSourceAdapter,
    KnowledgeBase,
    LibraryOfCongressAdapter,
    WikimediaCommonsAdapter,
)
from kathakaar.schemas import MediaAsset, SourceDocument, source_document_from_dict

ROOT = Path(__file__).resolve().parents[1]

CURATED_MEDIA = [
    SourceDocument(
        source_id="commons-hampi-stone-chariot",
        title="Stone Chariot, Hampi",
        place="Hampi, India",
        url="https://commons.wikimedia.org/wiki/File:Stone_Chariot,_Hampi_3.jpg",
        text="A public-domain photograph showing the Stone Chariot at Hampi.",
        publisher="Wikimedia Commons",
        license="Public domain",
        retrieved_at="2026-06-13",
        source_kind="open_media",
        rights_status="public_domain",
        attribution="Stone Chariot, Hampi 3, Prabhachatterji, Wikimedia Commons",
        review_status="curated",
        media_assets=(
            MediaAsset(
                asset_id="commons-hampi-stone-chariot-image",
                media_type="image",
                url=(
                    "https://upload.wikimedia.org/wikipedia/commons/b/b4/"
                    "Stone_Chariot%2C_Hampi_3.jpg"
                ),
                mime_type="image/jpeg",
                caption="Stone Chariot at Hampi",
                creator="Prabhachatterji",
                license="Public domain",
                rights_status="public_domain",
                attribution=("Stone Chariot, Hampi 3, Prabhachatterji, Wikimedia Commons"),
            ),
        ),
    ),
    SourceDocument(
        source_id="commons-timbuktu-sankore",
        title="Sankore Mosque, Timbuktu",
        place="Timbuktu, Mali",
        url=("https://commons.wikimedia.org/wiki/File:Fortier_368_Timbuktu_Sankore_Mosque.jpg"),
        text="A public-domain historic postcard view of Sankore Mosque in Timbuktu.",
        publisher="Wikimedia Commons",
        license="Public domain",
        retrieved_at="2026-06-13",
        source_kind="open_media",
        rights_status="public_domain",
        attribution="Sankore Mosque postcard, Edmond Fortier, Wikimedia Commons",
        review_status="curated",
        media_assets=(
            MediaAsset(
                asset_id="commons-timbuktu-sankore-image",
                media_type="image",
                url=(
                    "https://upload.wikimedia.org/wikipedia/commons/1/17/"
                    "Fortier_368_Timbuktu_Sankore_Mosque.jpg"
                ),
                mime_type="image/jpeg",
                caption="Historic view of Sankore Mosque in Timbuktu",
                creator="Edmond Fortier (1862-1928)",
                license="Public domain",
                rights_status="public_domain",
                attribution=("Sankore Mosque postcard, Edmond Fortier, Wikimedia Commons"),
            ),
        ),
    ),
    SourceDocument(
        source_id="loc-taj-mahal-92518904",
        title="Taj Mahal, Agra, India",
        place="Agra, India",
        url="https://www.loc.gov/item/92518904/",
        text="A 1927 photographic print of the Taj Mahal in Agra.",
        publisher="Library of Congress",
        license="No known restrictions on publication.",
        retrieved_at="2026-06-13",
        period="1927",
        source_kind="library_collection",
        rights_status="no_known_restrictions",
        attribution="Taj Mahal, Agra, India, Library of Congress",
        review_status="curated",
        media_assets=(
            MediaAsset(
                asset_id="loc-taj-mahal-92518904-image",
                media_type="image",
                url=(
                    "https://tile.loc.gov/storage-services/service/pnp/cph/"
                    "3b40000/3b40000/3b40300/3b40342r.jpg"
                ),
                mime_type="image/jpeg",
                caption="Taj Mahal, Agra, India, photographic print from 1927",
                license="No known restrictions on publication.",
                rights_status="no_known_restrictions",
                attribution="Taj Mahal, Agra, India, Library of Congress",
            ),
        ),
    ),
]


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser()
    command.add_argument(
        "--corpus",
        type=Path,
        default=ROOT / "benchmarks" / "grounding_v2" / "corpus.jsonl",
    )
    command.add_argument(
        "--output",
        type=Path,
        default=ROOT / "knowledge" / "kathakaar_v3.jsonl",
    )
    command.add_argument(
        "--online",
        action="store_true",
        help="Also fetch a small current sample from official collection APIs.",
    )
    command.add_argument(
        "--snapshot",
        type=Path,
        default=(ROOT / "knowledge" / "source_snapshots" / "official_collections_2026-06-13.jsonl"),
        help="Frozen official collection records used for offline rebuilds.",
    )
    return command


def main() -> None:
    args = parser().parse_args()
    knowledge = KnowledgeBase()
    for line in args.corpus.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        document = source_document_from_dict(json.loads(line))
        publisher = document.publisher or _publisher_for_url(document.url)
        knowledge.upsert(
            replace(
                document,
                publisher=publisher,
                license=document.license or "Source-linked factual summary",
                retrieved_at=document.retrieved_at or date.today().isoformat(),
                rights_status=(
                    "link_only" if document.rights_status == "unknown" else document.rights_status
                ),
                review_status=(
                    document.review_status if document.review_status != "unreviewed" else "curated"
                ),
            )
        )
    for document in CURATED_MEDIA:
        knowledge.upsert(document)

    if args.snapshot.exists():
        knowledge.ingest(JsonlSourceAdapter(args.snapshot))

    if args.online:
        online_documents = []
        online_documents.extend(
            LibraryOfCongressAdapter(
                query="Agra India",
                resource_format="photos",
                limit=3,
            ).fetch()
        )
        online_documents.extend(
            WikimediaCommonsAdapter(
                query="Hampi stone chariot",
                place="Hampi, India",
                limit=3,
            ).fetch()
        )
        online_documents.extend(
            WikimediaCommonsAdapter(
                query="Timbuktu Sankore mosque",
                place="Timbuktu, Mali",
                limit=3,
            ).fetch()
        )
        KnowledgeBase(online_documents).save(args.snapshot)
        for document in online_documents:
            knowledge.upsert(document)

    output_path = knowledge.save(args.output)
    audit = knowledge.audit()
    print(f"Wrote {audit.records} records and {audit.media_assets} media assets to {output_path}")
    print(json.dumps(audit.to_dict(), indent=2))
    if not audit.valid:
        raise SystemExit(2)


def _publisher_for_url(url: str) -> str:
    if "whc.unesco.org" in url:
        return "UNESCO World Heritage Centre"
    if "ich.unesco.org" in url:
        return "UNESCO Intangible Cultural Heritage"
    if "en.unesco.org" in url:
        return "UNESCO"
    return "Source publisher"


if __name__ == "__main__":
    main()
