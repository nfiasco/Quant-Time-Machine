"""Data versions: snapshots of the point-in-time store that runs can replay (S3.7).

A data version is the store as one completed ingestion run left it. Its manifest,
DATA_DIR/store/_versions/<data_version>.json, lists every Parquet file with its size and
SHA-256 hash, the rows per table and per source, and the latest `ingested_at` of any
row. The design is in doc/database-choice-review.md:

- **Written last.** `python -m app.data.ingest` writes a manifest only after its
  ingester finishes, so a run that fails part way, or stops at a rate limit, leaves no
  data version pointing at a partial batch. A run that adds nothing keeps the newest
  version instead of writing an identical one.
- **Named by when it was cut.** A data version is the UTC time its manifest was
  written, to the second, such as 20261101T143005Z. Within a store the names only
  increase, so the newest version sorts last.
- **A pinned view reads only its files.** `PointInTimeView(..., data_version=...)`
  reads only the files the manifest lists, and only rows ingested by its
  `ingested_through`, so data added later never changes a pinned answer. A listed file
  that's missing or changed raises DataVersionError instead.
- **Listed files are never deleted or rewritten.** `write_rows` never touches a stored
  file. Deleting a table to rebuild it breaks every data version that lists its files,
  and views pinned to them fail until the files are restored.

The API pins every request to the store's newest data version and echoes it
(app/api/conventions.py).
"""

import hashlib
import json
import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.data.errors import DataVersionError
from app.data.store import TableSpec, summarize, table_files
from app.data.tables import TABLES
from app.data.timeutil import to_utc

__all__ = [
    "DataVersionError",
    "Manifest",
    "latest_data_version",
    "open_version",
    "read_manifest",
    "write_manifest",
]

logger = logging.getLogger(__name__)

VERSIONS = "_versions"
"""The store's folder of manifests. Table names can't start with "_", so it never
clashes with a table."""

_NAME = re.compile(r"\d{8}T\d{6}Z", re.ASCII)
_NAME_FORMAT = "%Y%m%dT%H%M%SZ"


@dataclass(frozen=True)
class ManifestFile:
    """One Parquet file in a data version."""

    name: str
    """Its name in its table's folder."""
    size: int
    """In bytes."""
    sha256: str


@dataclass(frozen=True)
class ManifestTable:
    """One table in a data version."""

    rows: int
    sources: Mapping[str, int]
    """Rows per `source`, such as {"tiingo": 1234}."""
    files: tuple[ManifestFile, ...]


@dataclass(frozen=True)
class Manifest:
    """A data version: the store's files as one completed ingestion run left them."""

    data_version: str
    created_at: datetime
    written_by: str | None
    """The run that wrote it, such as "ingest tiingo"."""
    ingested_through: datetime
    """The latest `ingested_at` of any row in its files."""
    tables: Mapping[str, ManifestTable]
    """Only tables with files; a table not listed was empty."""

    @property
    def rows(self) -> int:
        return sum(table.rows for table in self.tables.values())

    @property
    def sources(self) -> dict[str, int]:
        """Rows per `source`, across every table."""
        counts: dict[str, int] = {}
        for table in self.tables.values():
            for source, rows in table.sources.items():
                counts[source] = counts.get(source, 0) + rows
        return dict(sorted(counts.items()))

    def paths(self, store: Path, table: str) -> list[Path]:
        """The files this version lists for `table`: none for a table it doesn't list."""
        listed = self.tables.get(table)
        return [] if listed is None else [store / table / f.name for f in listed.files]


def latest_data_version(store: Path) -> str | None:
    """The store's newest data version, or None if no ingestion run has written one."""
    names = [
        p.stem for p in (store / VERSIONS).glob("*.json") if _NAME.fullmatch(p.stem)
    ]
    return max(names, default=None)


def write_manifest(
    store: Path,
    tables: Iterable[TableSpec] | None = None,
    *,
    now: datetime | None = None,
    written_by: str | None = None,
) -> Manifest | None:
    """Freeze the store's files as a new data version, and return its manifest.

    `tables` defaults to every table in app/data/tables.py, and `now` to the current
    time. If the files are exactly the newest version's, nothing is written and that
    version is returned. A store without files has no data version: None.
    """
    created_at = datetime.now(UTC) if now is None else to_utc(now)
    listed: dict[str, ManifestTable] = {}
    ingested: list[datetime] = []
    for spec in TABLES.values() if tables is None else tables:
        files = table_files(store, spec)
        if not files:
            continue
        sources, latest = summarize(store, spec, files)
        listed[spec.name] = ManifestTable(
            rows=sum(sources.values()),
            sources=sources,
            files=tuple(
                ManifestFile(f.name, f.stat().st_size, _sha256(f)) for f in files
            ),
        )
        if latest is not None:
            ingested.append(latest)
    if not listed:
        logger.info("The store has no files yet, so there's no data version to write")
        return None

    newest = latest_data_version(store)
    if newest is not None:
        previous = read_manifest(store, newest)
        if _contents(previous.tables) == _contents(listed):
            logger.info("Data version %s is unchanged: this run added nothing", newest)
            return previous

    # Names only increase, even when the clock hasn't moved on a second since the last.
    cut = created_at.replace(microsecond=0)
    if newest is not None:
        last = datetime.strptime(newest, _NAME_FORMAT).replace(tzinfo=UTC)
        cut = max(cut, last + timedelta(seconds=1))
    manifest = Manifest(
        data_version=f"{cut:{_NAME_FORMAT}}",
        created_at=created_at,
        written_by=written_by,
        ingested_through=max(ingested, default=created_at),
        tables=listed,
    )

    # Write under a hidden name, then rename, so readers never see half a manifest.
    folder = store / VERSIONS
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{manifest.data_version}.json"
    partial = folder / f".{manifest.data_version}.json.tmp"
    try:
        text = json.dumps(_to_json(manifest), indent=2)
        partial.write_text(text + "\n", encoding="utf-8")
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    logger.info(
        "Data version %s: %d rows in %d files, ingested through %s",
        manifest.data_version,
        manifest.rows,
        sum(len(table.files) for table in listed.values()),
        f"{manifest.ingested_through:%Y-%m-%dT%H:%M:%SZ}",
    )
    return manifest


def read_manifest(store: Path, data_version: str) -> Manifest:
    """A data version's manifest. Raises DataVersionError if the store doesn't have it."""
    if not _NAME.fullmatch(data_version):
        raise DataVersionError(
            f"{data_version!r} isn't a data version; they look like 20261101T143005Z"
        )
    path = store / VERSIONS / f"{data_version}.json"
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DataVersionError(
            f"There's no data version {data_version} in {store}"
        ) from None
    return _from_json(content)


_verified: set[tuple[Path, str]] = set()
"""The data versions whose hashes this process has checked, by store and name."""


def open_version(store: Path, data_version: str) -> Manifest:
    """A data version's manifest, once its files are known to be intact.

    Every file it lists must exist with its recorded size, every time. The first time a
    version is opened in a process, each file's SHA-256 is checked as well; listed files
    never change, so later opens skip the hashing, which would otherwise slow every
    request as the store grows. Raises DataVersionError for a missing or changed file.
    """
    manifest = read_manifest(store, data_version)
    listed = [
        (f"{table}/{file.name}", store / table / file.name, file)
        for table, contents in manifest.tables.items()
        for file in contents.files
    ]
    gone = [name for name, path, _ in listed if not path.is_file()]
    if gone:
        raise DataVersionError(
            f"Data version {data_version} is missing files it lists: {_examples(gone)}. "
            f"{_NEVER_CHANGE}"
        )
    key = (store.resolve(), data_version)
    changed = [
        name
        for name, path, file in listed
        if path.stat().st_size != file.size
        or (key not in _verified and _sha256(path) != file.sha256)
    ]
    if changed:
        raise DataVersionError(
            f"Data version {data_version} lists files that changed after it was cut: "
            f"{_examples(changed)}. {_NEVER_CHANGE}"
        )
    _verified.add(key)
    return manifest


_NEVER_CHANGE = (
    "A data version's files must never be deleted or rewritten: restore them, or read "
    "a newer data version (each finished ingestion run writes one)."
)


def _sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _examples(names: list[str]) -> str:
    return ", ".join(names[:3]) + (
        f", and {len(names) - 3} more" if len(names) > 3 else ""
    )


def _contents(tables: Mapping[str, ManifestTable]) -> set[tuple[str, str, str]]:
    """Which files the tables hold, by table, name, and hash."""
    return {
        (table, file.name, file.sha256)
        for table, contents in tables.items()
        for file in contents.files
    }


def _timestamp(instant: datetime) -> str:
    return instant.isoformat().replace("+00:00", "Z")


def _to_json(manifest: Manifest) -> dict[str, Any]:
    return {
        "data_version": manifest.data_version,
        "created_at": _timestamp(manifest.created_at),
        "written_by": manifest.written_by,
        "ingested_through": _timestamp(manifest.ingested_through),
        "rows": manifest.rows,
        "sources": manifest.sources,
        "tables": {
            name: {
                "rows": table.rows,
                "sources": dict(table.sources),
                "files": [
                    {"name": f.name, "size": f.size, "sha256": f.sha256}
                    for f in table.files
                ],
            }
            for name, table in manifest.tables.items()
        },
    }


def _from_json(content: Mapping[str, Any]) -> Manifest:
    return Manifest(
        data_version=content["data_version"],
        created_at=to_utc(datetime.fromisoformat(content["created_at"])),
        written_by=content["written_by"],
        ingested_through=to_utc(datetime.fromisoformat(content["ingested_through"])),
        tables={
            name: ManifestTable(
                rows=table["rows"],
                sources=table["sources"],
                files=tuple(
                    ManifestFile(f["name"], f["size"], f["sha256"])
                    for f in table["files"]
                ),
            )
            for name, table in content["tables"].items()
        },
    )
