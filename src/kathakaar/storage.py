"""Optional production persistence for canonical records and media vectors."""

from __future__ import annotations

import json
import uuid
from typing import Any, cast
from urllib.request import Request, urlopen

from kathakaar.multimodal import MultimodalRetriever
from kathakaar.schemas import SourceDocument, source_document_from_dict


class PostgresKnowledgeStore:
    """Store normalized source records as versioned JSONB documents."""

    def __init__(self, dsn: str) -> None:
        if not dsn.strip():
            raise ValueError("PostgreSQL DSN is required")
        self.dsn = dsn

    def initialize(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS kathakaar_sources (
                    source_id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    place TEXT NOT NULL,
                    publisher TEXT NOT NULL,
                    rights_status TEXT NOT NULL,
                    document JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

    def sync(self, documents: list[SourceDocument]) -> int:
        self.initialize()
        rows = [
            (
                document.source_id,
                document.content_hash,
                document.place,
                document.publisher,
                document.rights_status,
                json.dumps(document.to_dict()),
            )
            for document in documents
        ]
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO kathakaar_sources (
                    source_id,
                    content_hash,
                    place,
                    publisher,
                    rights_status,
                    document
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (source_id) DO UPDATE SET
                    content_hash = EXCLUDED.content_hash,
                    place = EXCLUDED.place,
                    publisher = EXCLUDED.publisher,
                    rights_status = EXCLUDED.rights_status,
                    document = EXCLUDED.document,
                    updated_at = NOW()
                """,
                rows,
            )
        return len(rows)

    def load(self) -> list[SourceDocument]:
        self.initialize()
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT document FROM kathakaar_sources ORDER BY source_id")
            return [
                source_document_from_dict(
                    row[0] if isinstance(row[0], dict) else json.loads(row[0])
                )
                for row in cursor.fetchall()
            ]

    def _connect(self) -> Any:
        try:
            import psycopg  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "Install kathakaar[production] to use PostgreSQL persistence."
            ) from exc
        return psycopg.connect(self.dsn)


class QdrantMediaStore:
    """Push fitted media vectors to Qdrant through its REST API."""

    def __init__(
        self,
        base_url: str,
        collection: str = "kathakaar_media",
        api_key: str = "",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def sync(self, retriever: MultimodalRetriever) -> int:
        points = qdrant_points(retriever)
        if not points:
            return 0
        self._request(
            "PUT",
            f"/collections/{self.collection}",
            {
                "vectors": {
                    "size": retriever.encoder.dimensions,
                    "distance": "Cosine",
                }
            },
        )
        self._request(
            "PUT",
            f"/collections/{self.collection}/points?wait=true",
            {"points": points},
        )
        return len(points)

    def search(self, vector: list[float], limit: int = 5) -> list[dict[str, Any]]:
        payload = self._request(
            "POST",
            f"/collections/{self.collection}/points/query",
            {
                "query": vector,
                "limit": limit,
                "with_payload": True,
            },
        )
        result = payload.get("result", {})
        points = result.get("points", result) if isinstance(result, dict) else result
        return cast(list[dict[str, Any]], points if isinstance(points, list) else [])

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            method=method,
            headers=headers,
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Qdrant returned a non-object response")
        return cast(dict[str, Any], value)


def qdrant_points(retriever: MultimodalRetriever) -> list[dict[str, Any]]:
    documents = {document.source_id: document for document in retriever.documents}
    points: list[dict[str, Any]] = []
    namespace = uuid.UUID("e0e5b257-e508-4b55-b8f7-5ea86acc9308")
    for asset_id, vector in sorted(retriever.asset_vectors.items()):
        source_id, asset = retriever.asset_lookup[asset_id]
        document = documents[source_id]
        points.append(
            {
                "id": str(uuid.uuid5(namespace, asset_id)),
                "vector": vector,
                "payload": {
                    "asset_id": asset_id,
                    "source_id": source_id,
                    "title": document.title,
                    "place": document.place,
                    "media_type": asset.media_type,
                    "url": asset.url,
                    "rights_status": asset.rights_status,
                    "license": asset.license,
                    "attribution": asset.attribution,
                    "content_hash": document.content_hash,
                },
            }
        )
    return points
