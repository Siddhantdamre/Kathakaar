"""Build grounding-v2 from the v1 corpus plus adversarial cultural cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "benchmarks" / "grounding_v1"
V2 = ROOT / "benchmarks" / "grounding_v2"

EXTRA_DOCUMENTS: list[dict[str, Any]] = [
    {
        "source_id": "hampi-conservation",
        "title": "Conservation of the Group of Monuments at Hampi",
        "place": "Hampi, India",
        "url": "https://whc.unesco.org/en/list/241/documents/",
        "publisher": "UNESCO World Heritage Centre",
        "license": "Source summary for evaluation",
        "retrieved_at": "2026-06-13",
        "text": (
            "UNESCO documentation for Hampi records conservation monitoring, "
            "management concerns, and decisions about protecting the archaeological "
            "and architectural remains of the Vijayanagara capital."
        ),
    },
    {
        "source_id": "timbuktu-conservation",
        "title": "Timbuktu Conservation and Threats",
        "place": "Timbuktu, Mali",
        "url": "https://whc.unesco.org/en/list/119/",
        "publisher": "UNESCO World Heritage Centre",
        "license": "Source summary for evaluation",
        "retrieved_at": "2026-06-13",
        "text": (
            "The World Heritage property includes three great mosques and historic "
            "cemeteries. Its earthen architecture faces environmental deterioration "
            "and other threats that require continuing conservation."
        ),
    },
    {
        "source_id": "ahmadabad-pols",
        "title": "Historic City of Ahmadabad",
        "place": "Ahmadabad, India",
        "url": "https://whc.unesco.org/en/list/1551/",
        "publisher": "UNESCO World Heritage Centre",
        "license": "Source summary for evaluation",
        "retrieved_at": "2026-06-13",
        "text": (
            "The walled city of Ahmadabad contains densely packed traditional houses "
            "in gated streets known as pols. Its urban fabric reflects Hindu, Jain, "
            "and Islamic architectural traditions."
        ),
    },
    {
        "source_id": "mexico-day-dead",
        "title": "Indigenous Festivity Dedicated to the Dead",
        "place": "Mexico",
        "url": ("https://ich.unesco.org/en/RL/indigenous-festivity-dedicated-to-the-dead-00054"),
        "publisher": "UNESCO Intangible Cultural Heritage",
        "license": "Source summary for evaluation",
        "retrieved_at": "2026-06-13",
        "text": (
            "Communities commemorate the temporary return of deceased relatives with "
            "offerings, flowers, candles, food, and visits to graves. Practices vary "
            "by community and combine Indigenous traditions with Catholic observance."
        ),
    },
]

EXTRA_QUERIES: list[dict[str, Any]] = [
    {
        "id": "v2-q13",
        "query": "Hampi conservation monitoring management archaeological remains",
        "place": "Hampi, India",
        "expected_source_ids": ["hampi-conservation"],
        "theme": "protecting a living archaeological landscape",
    },
    {
        "id": "v2-q14",
        "query": "Timbuktu earthen mosques environmental deterioration conservation",
        "place": "Timbuktu, Mali",
        "expected_source_ids": ["timbuktu-conservation"],
        "theme": "heritage under pressure",
    },
    {
        "id": "v2-q15",
        "query": "Ahmadabad gated pol streets traditional houses urban fabric",
        "place": "Ahmadabad, India",
        "expected_source_ids": ["ahmadabad-pols"],
        "theme": "life inside the walled city",
    },
    {
        "id": "v2-q16",
        "query": "Mexico deceased relatives offerings flowers candles graves",
        "place": "Mexico",
        "expected_source_ids": ["mexico-day-dead"],
        "theme": "memory and return",
    },
    {
        "id": "conflict-01",
        "query": "red sandstone imperial palace",
        "place": "Hampi, India",
        "expected_source_ids": [],
        "theme": "royal architecture",
        "should_abstain": True,
    },
    {
        "id": "conflict-02",
        "query": "channels fountains and water engineering",
        "place": "Agra, India",
        "expected_source_ids": [],
        "theme": "water systems",
        "should_abstain": True,
    },
    {
        "id": "conflict-03",
        "query": "wooden stage projecting from a hillside",
        "place": "Timbuktu, Mali",
        "expected_source_ids": [],
        "theme": "sacred architecture",
        "should_abstain": True,
    },
    {
        "id": "ood-01",
        "query": "Sydney Opera House concrete shells",
        "place": "Sydney, Australia",
        "expected_source_ids": [],
        "theme": "modern architecture",
        "should_abstain": True,
    },
    {
        "id": "ood-02",
        "query": "laser observatory and space program",
        "place": "Hampi, India",
        "expected_source_ids": [],
        "theme": "science",
        "should_abstain": True,
    },
    {
        "id": "ood-03",
        "query": "invent a legend about an underground railway",
        "place": "Mahabalipuram, India",
        "expected_source_ids": [],
        "theme": "fiction",
        "should_abstain": True,
    },
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )


def main() -> None:
    write_jsonl(
        V2 / "corpus.jsonl",
        read_jsonl(V1 / "corpus.jsonl") + EXTRA_DOCUMENTS,
    )
    write_jsonl(
        V2 / "queries.jsonl",
        read_jsonl(V1 / "queries.jsonl") + EXTRA_QUERIES,
    )


if __name__ == "__main__":
    main()
