"""Normalized, provenance-first cultural knowledge base and source adapters."""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

from kathakaar.net import download_json
from kathakaar.schemas import MediaAsset, SourceDocument, source_document_from_dict

RIGHTS_STATUSES = frozenset(
    {
        "open",
        "public_domain",
        "no_known_restrictions",
        "link_only",
        "permission_required",
        "unknown",
    }
)


@dataclass(frozen=True)
class ValidationIssue:
    source_id: str
    severity: str
    message: str


@dataclass(frozen=True)
class KnowledgeAudit:
    records: int
    media_assets: int
    duplicate_hashes: int
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": self.records,
            "media_assets": self.media_assets,
            "duplicate_hashes": self.duplicate_hashes,
            "valid": self.valid,
            "issues": [
                {
                    "source_id": issue.source_id,
                    "severity": issue.severity,
                    "message": issue.message,
                }
                for issue in self.issues
            ],
        }


class SourceAdapter(Protocol):
    def fetch(self) -> list[SourceDocument]:
        """Fetch normalized cultural records."""


class KnowledgeBase:
    """Deterministic JSONL knowledge store with validation and deduplication."""

    def __init__(self, documents: list[SourceDocument] | None = None) -> None:
        self._documents: dict[str, SourceDocument] = {}
        for document in documents or []:
            self.upsert(document)

    @property
    def documents(self) -> list[SourceDocument]:
        return [self._documents[key] for key in sorted(self._documents)]

    def upsert(self, document: SourceDocument) -> None:
        normalized = with_content_hash(document)
        self._documents[normalized.source_id] = normalized

    def ingest(self, adapter: SourceAdapter) -> int:
        documents = adapter.fetch()
        for document in documents:
            self.upsert(document)
        return len(documents)

    def audit(self) -> KnowledgeAudit:
        issues: list[ValidationIssue] = []
        hash_counts: dict[str, int] = {}
        media_count = 0

        for document in self.documents:
            media_count += len(document.media_assets)
            if not document.title.strip():
                issues.append(ValidationIssue(document.source_id, "error", "Missing title."))
            if not document.place.strip():
                issues.append(ValidationIssue(document.source_id, "error", "Missing place."))
            if not document.url.startswith(("http://", "https://")):
                issues.append(
                    ValidationIssue(document.source_id, "error", "Source URL is not HTTP(S).")
                )
            if not document.publisher.strip():
                issues.append(
                    ValidationIssue(document.source_id, "warning", "Publisher is not recorded.")
                )
            if not document.retrieved_at.strip():
                issues.append(
                    ValidationIssue(
                        document.source_id, "warning", "Retrieval date is not recorded."
                    )
                )
            if document.rights_status not in RIGHTS_STATUSES:
                issues.append(
                    ValidationIssue(
                        document.source_id,
                        "error",
                        f"Unsupported rights status: {document.rights_status}",
                    )
                )
            if document.rights_status in {"unknown", "permission_required"}:
                issues.append(
                    ValidationIssue(
                        document.source_id,
                        "warning",
                        "Record may be indexed as link-only but should not be republished.",
                    )
                )
            expected_hash = compute_content_hash(document)
            if document.content_hash != expected_hash:
                issues.append(
                    ValidationIssue(document.source_id, "error", "Content hash does not match.")
                )
            hash_counts[document.content_hash] = hash_counts.get(document.content_hash, 0) + 1

            for asset in document.media_assets:
                issues.extend(_validate_asset(document.source_id, asset))

        duplicate_hashes = sum(count - 1 for count in hash_counts.values() if count > 1)
        return KnowledgeAudit(
            records=len(self._documents),
            media_assets=media_count,
            duplicate_hashes=duplicate_hashes,
            issues=tuple(issues),
        )

    def save(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            "".join(
                json.dumps(document.to_dict(), ensure_ascii=True, separators=(",", ":")) + "\n"
                for document in self.documents
            ),
            encoding="utf-8",
        )
        return output_path

    @classmethod
    def load(cls, path: str | Path) -> KnowledgeBase:
        documents = [
            source_document_from_dict(json.loads(line))
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not documents:
            raise ValueError(f"knowledge base is empty: {path}")
        return cls(documents)


class JsonlSourceAdapter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch(self) -> list[SourceDocument]:
        return [
            source_document_from_dict(json.loads(line))
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


class LibraryOfCongressAdapter:
    """Fetch rights-aware records from the official loc.gov JSON API."""

    base_url = "https://www.loc.gov"

    def __init__(
        self,
        query: str,
        resource_format: str = "photos",
        limit: int = 10,
        timeout_seconds: float = 30.0,
        retries: int = 3,
    ) -> None:
        self.query = query
        self.resource_format = resource_format.strip("/")
        self.limit = max(1, min(limit, 100))
        self.timeout_seconds = timeout_seconds
        self.retries = max(1, retries)

    def fetch(self) -> list[SourceDocument]:
        params = urlencode({"q": self.query, "fo": "json", "c": self.limit})
        payload = self._get_json(f"{self.base_url}/{self.resource_format}/?{params}")
        documents: list[SourceDocument] = []
        for result in payload.get("results", [])[: self.limit]:
            item_url = str(result.get("id", "")).replace("http://", "https://")
            if not item_url:
                continue
            detail = self._get_json(f"{item_url}?fo=json")
            documents.append(self.parse_item(detail, fallback=result))
        return documents

    def parse_item(
        self,
        payload: dict[str, Any],
        fallback: dict[str, Any] | None = None,
    ) -> SourceDocument:
        item = dict(fallback or {})
        item.update(payload.get("item", {}))
        source_url = str(item.get("id", "")).replace("http://", "https://")
        if not source_url:
            raise ValueError("Library of Congress item is missing an id")
        source_id = f"loc-{source_url.rstrip('/').split('/')[-1]}"
        title = str(item.get("title") or "Untitled Library of Congress item")
        descriptions = item.get("description") or []
        text = " ".join(str(value) for value in descriptions).strip() or title
        rights = str(
            item.get("rights_information")
            or item.get("rights_advisory")
            or "Rights status not supplied by source."
        )
        rights_status = (
            "no_known_restrictions" if "no known restrictions" in rights.lower() else "unknown"
        )
        media_assets = self._parse_resources(
            payload.get("resources", []),
            source_id=source_id,
            title=title,
            rights=rights,
            rights_status=rights_status,
        )
        locations = item.get("location") or item.get("locations") or []
        place = _first_text(locations) or self.query
        languages = item.get("language") or []
        return SourceDocument(
            source_id=source_id,
            title=title,
            place=place,
            url=source_url,
            text=text,
            publisher="Library of Congress",
            license=rights,
            retrieved_at=date.today().isoformat(),
            language=_first_text(languages) or "en",
            period=str(item.get("date") or ""),
            source_kind="library_collection",
            rights_status=rights_status,
            attribution=f"{title}, Library of Congress",
            review_status="machine_ingested",
            media_assets=tuple(media_assets),
        )

    def _get_json(self, url: str) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Kathakaar/0.3 (cultural research prototype)",
        }
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return download_json(url, headers, self.timeout_seconds)
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(0.25 * (2**attempt))
        raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error

    @staticmethod
    def _parse_resources(
        resources: list[dict[str, Any]],
        source_id: str,
        title: str,
        rights: str,
        rights_status: str,
    ) -> list[MediaAsset]:
        assets: list[MediaAsset] = []
        for resource_index, resource in enumerate(resources):
            files = _flatten_file_records(resource.get("files", []))
            candidates = [
                file
                for file in files
                if str(file.get("mimetype", "")).startswith(("image/", "audio/", "video/"))
            ]
            if not candidates and resource.get("image"):
                candidates = [
                    {
                        "url": resource["image"],
                        "mimetype": "image/jpeg",
                    }
                ]
            if not candidates:
                continue
            candidate = max(candidates, key=lambda file: int(file.get("size") or 0))
            mime_type = str(candidate.get("mimetype", ""))
            assets.append(
                MediaAsset(
                    asset_id=f"{source_id}-asset-{resource_index + 1}",
                    media_type=mime_type.split("/", maxsplit=1)[0] or "document",
                    url=str(candidate.get("url", "")),
                    mime_type=mime_type,
                    caption=str(resource.get("caption") or title),
                    license=rights,
                    rights_status=rights_status,
                    attribution=f"{title}, Library of Congress",
                )
            )
        return assets


class WikimediaCommonsAdapter:
    """Fetch openly licensed media with attribution from Wikimedia Commons."""

    api_url = "https://commons.wikimedia.org/w/api.php"

    def __init__(
        self,
        query: str,
        place: str,
        limit: int = 10,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.query = query
        self.place = place
        self.limit = max(1, min(limit, 50))
        self.timeout_seconds = timeout_seconds

    def fetch(self) -> list[SourceDocument]:
        params = urlencode(
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": self.query,
                "gsrnamespace": 6,
                "gsrlimit": self.limit,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "format": "json",
                "origin": "*",
            }
        )
        payload = download_json(
            f"{self.api_url}?{params}",
            headers={
                "Accept": "application/json",
                "User-Agent": "Kathakaar/0.3 (cultural research prototype)",
            },
            timeout_seconds=self.timeout_seconds,
        )
        pages = payload.get("query", {}).get("pages", {})
        return [self.parse_page(page) for page in pages.values() if page.get("imageinfo")][
            : self.limit
        ]

    def parse_page(self, page: dict[str, Any]) -> SourceDocument:
        image_info = page["imageinfo"][0]
        metadata = image_info.get("extmetadata", {})
        title = str(page.get("title") or "Wikimedia Commons media").removeprefix("File:")
        description = _strip_html(_metadata_value(metadata, "ImageDescription")) or title
        artist = _strip_html(_metadata_value(metadata, "Artist"))
        license_name = _metadata_value(metadata, "LicenseShortName") or "Unknown"
        license_url = _metadata_value(metadata, "LicenseUrl")
        usage_terms = _metadata_value(metadata, "UsageTerms")
        source_url = str(
            image_info.get("descriptionurl")
            or f"https://commons.wikimedia.org/wiki/{str(page.get('title', '')).replace(' ', '_')}"
        )
        media_url = str(image_info.get("url") or "")
        source_id = (
            f"commons-{page.get('pageid', hashlib.sha256(source_url.encode()).hexdigest()[:12])}"
        )
        rights_status = (
            "public_domain"
            if "public domain" in license_name.lower()
            else "open"
            if license_url or "creative commons" in usage_terms.lower()
            else "unknown"
        )
        attribution = ", ".join(value for value in (title, artist, "Wikimedia Commons") if value)
        mime_type = _mime_from_url(media_url)
        asset = MediaAsset(
            asset_id=f"{source_id}-image-1",
            media_type="image",
            url=media_url,
            mime_type=mime_type,
            caption=description,
            creator=artist,
            license=license_name,
            rights_status=rights_status,
            attribution=attribution,
        )
        return SourceDocument(
            source_id=source_id,
            title=title,
            place=self.place,
            url=source_url,
            text=description,
            publisher="Wikimedia Commons",
            license=license_name,
            retrieved_at=date.today().isoformat(),
            source_kind="open_media",
            rights_uri=license_url,
            rights_status=rights_status,
            attribution=attribution,
            review_status="machine_ingested",
            media_assets=(asset,),
        )


class IIIFManifestAdapter:
    """Parse a IIIF Presentation 3 manifest from a URL or local JSON file."""

    def __init__(self, location: str, timeout_seconds: float = 30.0) -> None:
        self.location = location
        self.timeout_seconds = timeout_seconds

    def fetch(self) -> list[SourceDocument]:
        payload = self._load()
        label = _language_map_text(payload.get("label")) or "Untitled IIIF object"
        metadata = {
            _language_map_text(item.get("label")): _language_map_text(item.get("value"))
            for item in payload.get("metadata", [])
        }
        source_url = str(payload.get("id") or self.location)
        source_id = "iiif-" + hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:16]
        rights_uri = str(payload.get("rights") or "")
        assets = tuple(_iiif_assets(payload, source_id, rights_uri, label))
        summary = _language_map_text(payload.get("summary"))
        provider = _provider_name(payload.get("provider", []))
        return [
            SourceDocument(
                source_id=source_id,
                title=label,
                place=metadata.get("Place", metadata.get("Location", "Unknown")),
                url=source_url,
                text=summary or label,
                publisher=provider or "IIIF provider",
                license=rights_uri,
                retrieved_at=date.today().isoformat(),
                language=str(payload.get("language") or "en"),
                source_kind="iiif_manifest",
                rights_uri=rights_uri,
                rights_status="open" if "creativecommons.org" in rights_uri else "unknown",
                attribution=provider,
                review_status="machine_ingested",
                media_assets=assets,
            )
        ]

    def _load(self) -> dict[str, Any]:
        path = Path(self.location)
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("IIIF manifest must be a JSON object")
            return payload
        return download_json(
            self.location,
            headers={
                "Accept": "application/ld+json, application/json",
                "User-Agent": "Kathakaar/0.3 (IIIF client)",
            },
            timeout_seconds=self.timeout_seconds,
        )


def compute_content_hash(document: SourceDocument) -> str:
    payload = {
        "title": document.title,
        "place": document.place,
        "url": document.url,
        "text": document.text,
        "publisher": document.publisher,
        "period": document.period,
        "media_assets": [
            {
                "asset_id": asset.asset_id,
                "url": asset.url,
                "caption": asset.caption,
                "transcript": asset.transcript,
                "sha256": asset.sha256,
            }
            for asset in document.media_assets
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def with_content_hash(document: SourceDocument) -> SourceDocument:
    payload = document.to_dict()
    payload["content_hash"] = ""
    normalized = source_document_from_dict(payload)
    payload["content_hash"] = compute_content_hash(normalized)
    return source_document_from_dict(payload)


def _validate_asset(source_id: str, asset: MediaAsset) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if asset.media_type not in {"image", "audio", "video", "document"}:
        issues.append(
            ValidationIssue(source_id, "error", f"Unsupported media type: {asset.media_type}")
        )
    if not asset.url and not asset.local_path:
        issues.append(ValidationIssue(source_id, "error", "Media asset has no location."))
    if asset.rights_status not in RIGHTS_STATUSES:
        issues.append(
            ValidationIssue(
                source_id,
                "error",
                f"Unsupported media rights status: {asset.rights_status}",
            )
        )
    if asset.rights_status in {"open", "no_known_restrictions"} and not asset.attribution:
        issues.append(
            ValidationIssue(source_id, "warning", "Reusable media asset lacks attribution.")
        )
    return issues


def _flatten_file_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        return []
    flattened: list[dict[str, Any]] = []
    for item in value:
        flattened.extend(_flatten_file_records(item))
    return flattened


def _first_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _first_text(value[0])
    if isinstance(value, dict):
        return _language_map_text(value)
    return ""


def _language_map_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_language_map_text(item) for item in value).strip()
    if isinstance(value, dict):
        for key in ("en", "none"):
            if key in value:
                return _language_map_text(value[key])
        if value:
            return _language_map_text(next(iter(value.values())))
    return ""


def _provider_name(providers: Any) -> str:
    if not isinstance(providers, list):
        return ""
    return "; ".join(
        value
        for provider in providers
        if isinstance(provider, dict)
        for value in [_language_map_text(provider.get("label"))]
        if value
    )


def _iiif_assets(
    manifest: dict[str, Any],
    source_id: str,
    rights_uri: str,
    title: str,
) -> list[MediaAsset]:
    assets: list[MediaAsset] = []
    for canvas_index, canvas in enumerate(manifest.get("items", [])):
        canvas_label = _language_map_text(canvas.get("label")) or title
        for page in canvas.get("items", []):
            for annotation in page.get("items", []):
                body = annotation.get("body", {})
                if not isinstance(body, dict) or not body.get("id"):
                    continue
                mime_type = str(body.get("format") or "")
                media_type = mime_type.split("/", maxsplit=1)[0] or "image"
                assets.append(
                    MediaAsset(
                        asset_id=f"{source_id}-canvas-{canvas_index + 1}",
                        media_type=media_type,
                        url=str(body["id"]),
                        mime_type=mime_type,
                        caption=canvas_label,
                        license=rights_uri,
                        rights_status=(
                            "open" if "creativecommons.org" in rights_uri else "unknown"
                        ),
                        attribution=title,
                    )
                )
    return assets


def _metadata_value(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key, {})
    return str(value.get("value") or "") if isinstance(value, dict) else ""


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _mime_from_url(url: str) -> str:
    clean_url = url.lower().split("?", maxsplit=1)[0]
    for suffix, mime_type in (
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".png", "image/png"),
        (".webp", "image/webp"),
        (".gif", "image/gif"),
        (".tif", "image/tiff"),
        (".tiff", "image/tiff"),
    ):
        if clean_url.endswith(suffix):
            return mime_type
    return "application/octet-stream"
