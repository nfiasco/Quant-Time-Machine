"""The raw cache: every response ingestion downloads, saved as it was returned (S3.4).

Responses live under DATA_DIR/raw/<source>/, two files per request:

    <sha[:2]>/<sha>.body   the response body, byte for byte
    <sha[:2]>/<sha>.json   what was asked and when: the method, the URL without secrets,
                           the status, fetched_at (UTC), the content type and length,
                           the body's SHA-256, and a few response headers

`sha` is the SHA-256 of the request's method and URL, with the query sorted and secrets
removed, so the same request always maps to the same files. Request headers are never
saved, and secret query parameters (`api_key`, `apikey`, `token`) are removed from every
saved URL. Only successful responses are cached. A refresh overwrites the entry.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.data.timeutil import to_utc

SECRET_PARAMS = frozenset({"api_key", "apikey", "token"})
"""Query parameters that carry credentials, removed from every saved URL."""

SAVED_HEADERS = ("content-type", "date", "etag", "last-modified")
"""Response headers worth keeping for provenance."""


def redact_url(url: str) -> str:
    """The URL with its query sorted and secret parameters removed."""
    parts = urlsplit(url)
    query = sorted(
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name.lower() not in SECRET_PARAMS
    )
    return urlunsplit(parts._replace(query=urlencode(query)))


@dataclass(frozen=True)
class CachedResponse:
    """A response saved in the raw cache."""

    url: str
    """The request URL, without secrets."""
    status_code: int
    fetched_at: datetime
    content_type: str | None
    content: bytes
    path: Path
    """The file holding the body."""

    def json(self) -> Any:
        return json.loads(self.content)


class RawCache:
    """The cached responses of one source, under DATA_DIR/raw/<source>/."""

    def __init__(self, raw_dir: Path, source: str) -> None:
        self.source = source
        self.directory = raw_dir / source

    def get(self, method: str, url: str) -> CachedResponse | None:
        """The cached response to this request, or None if there isn't one."""
        body, metadata = self._paths(method, url)
        if not metadata.exists():
            return None
        return self._load(body, metadata)

    def put(
        self,
        method: str,
        url: str,
        *,
        status_code: int,
        content: bytes,
        headers: Mapping[str, str],
        fetched_at: datetime,
    ) -> CachedResponse:
        """Save a response, replacing any earlier one to the same request."""
        body, metadata = self._paths(method, url)
        headers = {name.lower(): value for name, value in headers.items()}
        record = {
            "source": self.source,
            "method": method.upper(),
            "url": redact_url(url),
            "status_code": status_code,
            "fetched_at": to_utc(fetched_at).isoformat(),
            "content_type": headers.get("content-type"),
            "content_length": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "headers": {
                name: headers[name] for name in SAVED_HEADERS if name in headers
            },
        }
        body.parent.mkdir(parents=True, exist_ok=True)
        # The body goes first: an entry counts as cached once its metadata exists.
        _write_atomically(body, content)
        _write_atomically(metadata, json.dumps(record, indent=2).encode())
        return self._load(body, metadata)

    def fetch_times(self, since: datetime) -> list[datetime]:
        """When each cached response fetched at or after `since` was fetched, oldest first."""
        times = []
        for metadata in self.directory.glob("*/*.json"):
            fetched_at = datetime.fromisoformat(
                json.loads(metadata.read_text(encoding="utf-8"))["fetched_at"]
            )
            if fetched_at >= since:
                times.append(fetched_at)
        return sorted(times)

    def _paths(self, method: str, url: str) -> tuple[Path, Path]:
        request = f"{method.upper()} {redact_url(url)}"
        sha = hashlib.sha256(request.encode()).hexdigest()
        folder = self.directory / sha[:2]
        return folder / f"{sha}.body", folder / f"{sha}.json"

    @staticmethod
    def _load(body: Path, metadata: Path) -> CachedResponse:
        record = json.loads(metadata.read_text(encoding="utf-8"))
        return CachedResponse(
            url=record["url"],
            status_code=record["status_code"],
            fetched_at=datetime.fromisoformat(record["fetched_at"]),
            content_type=record["content_type"],
            content=body.read_bytes(),
            path=body,
        )


def _write_atomically(path: Path, content: bytes) -> None:
    partial = path.with_name(f".{path.name}.tmp")
    partial.write_bytes(content)
    partial.replace(path)
