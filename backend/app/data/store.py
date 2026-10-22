"""The point-in-time store: append-only Parquet tables under DATA_DIR/store/<table>/.

Decision D1 (doc/storage.md). Each table is a folder of immutable Parquet files, and
every row carries what it describes (the table's key and values) plus provenance:

- `source`: where it came from, such as "alfred", "edgar", or "tiingo" (the names
  doc/api-v1.md shows)
- `source_ref`: the exact reference, such as a URL, an accession number, or a vintage
- `available_at`: when the world could first know it (doc/time-model.md)
- `ingested_at`: when this store saved it, set by `write_rows`
- `time_assumed`: whether `available_at` was assumed rather than published (rule 11)

(key, `available_at`) is unique: a revision is a new row with a later `available_at`,
never an overwrite. Read the store through `PointInTimeView` (app/data/view.py). This
module is the only one that opens DuckDB or reads Parquet files.

Changing how a table's `available_at` is computed means rebuilding the table: delete
DATA_DIR/store/<table>/ and re-run ingestion, which reuses the raw cache.
"""

import logging
import math
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from app.data.timeutil import to_utc

logger = logging.getLogger(__name__)

PROVENANCE_COLUMNS: Mapping[str, str] = {
    "source": "VARCHAR",
    "source_ref": "VARCHAR",
    "available_at": "TIMESTAMPTZ",
    "ingested_at": "TIMESTAMPTZ",
    "time_assumed": "BOOLEAN",
}
"""The columns every table has after its own, with their DuckDB types."""

# Column types a table can use, and the pandas dtype that carries each one into DuckDB.
# The nullable dtypes keep None as NULL; plain float64 would turn it into NaN.
_PANDAS_DTYPES: Mapping[str, str] = {
    "VARCHAR": "object",
    "DATE": "object",
    "TIMESTAMPTZ": "datetime64[us, UTC]",
    "DOUBLE": "Float64",
    "BIGINT": "Int64",
    "BOOLEAN": "boolean",
}

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]*", re.ASCII)


class StoreError(ValueError):
    """Rows that can't be written, such as a naive timestamp or a missing column."""


@dataclass(frozen=True)
class TableSpec:
    """One table in the store.

    `key` names what a row describes, for example ("series_id", "observation_date").
    Versions of the same thing differ by `available_at`, so (key, `available_at`) is
    unique. `columns` maps each of the table's own columns, key included, to its type:
    VARCHAR, DATE, TIMESTAMPTZ, DOUBLE, BIGINT, or BOOLEAN.
    """

    name: str
    key: tuple[str, ...]
    columns: Mapping[str, str]

    def __post_init__(self) -> None:
        # Names end up in SQL, so they must be plain identifiers.
        unsafe = [n for n in (self.name, *self.columns) if not _IDENTIFIER.fullmatch(n)]
        if unsafe:
            raise ValueError(f"not lowercase identifiers: {unsafe}")
        if not self.key or not set(self.key) <= set(self.columns):
            raise ValueError(
                f"{self.name}: the key must be some of the table's columns"
            )
        if clash := sorted(set(self.columns) & set(PROVENANCE_COLUMNS)):
            raise ValueError(f"{self.name}: {clash} are provenance columns")
        if unknown := sorted(set(self.columns.values()) - set(_PANDAS_DTYPES)):
            raise ValueError(f"{self.name}: unsupported column types {unknown}")

    @property
    def all_columns(self) -> dict[str, str]:
        """The table's own columns, then the provenance columns."""
        return {**self.columns, **PROVENANCE_COLUMNS}


@dataclass(frozen=True)
class WriteResult:
    """What `write_rows` did."""

    table: str
    written: int
    """New rows saved."""
    skipped: int
    """Rows already stored with the same values."""
    conflicts: int
    """Rows already stored with different values. The stored rows were kept."""
    path: Path | None
    """The new Parquet file, or None if nothing was new."""


def store_dir(data_dir: Path) -> Path:
    """Where the point-in-time store lives: DATA_DIR/store."""
    return data_dir / "store"


def connect() -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection that returns TIMESTAMPTZ values in UTC.

    Without `SET TimeZone`, DuckDB uses the machine's time zone, so the same query
    would return New York times on a laptop and UTC times on CI.
    """
    connection = duckdb.connect()
    connection.execute("SET TimeZone = 'UTC'")
    return connection


def table_files(store: Path, spec: TableSpec) -> list[Path]:
    """The table's Parquet files, oldest first (file names start with `ingested_at`)."""
    return sorted((store / spec.name).glob("part-*.parquet"))


def table_source(store: Path, spec: TableSpec) -> str:
    """SQL for every row of a table, to use after FROM.

    It names the files explicitly, so a reader sees a fixed set of files even while new
    ones are written. A table with no files yet is an empty, typed result rather than
    the error a glob that matches nothing would raise.
    """
    files = table_files(store, spec)
    if not files:
        nulls = ", ".join(f"NULL::{t} AS {c}" for c, t in spec.all_columns.items())
        return f"(SELECT {nulls} WHERE false)"
    return f"read_parquet([{', '.join(sql_string(str(f)) for f in files)}])"


def sql_string(text: str) -> str:
    """A SQL string literal."""
    return "'" + text.replace("'", "''") + "'"


def sql_timestamp(instant: datetime) -> str:
    """A SQL TIMESTAMPTZ literal for an aware datetime."""
    return f"TIMESTAMPTZ {sql_string(to_utc(instant).isoformat())}"


def max_per_group(
    store: Path, spec: TableSpec, column: str, *, group: str
) -> dict[Any, Any]:
    """The largest `column` among stored rows, for each value of `group`.

    For ingesters deciding what to download next, such as each security's last stored
    session. It reads every stored row, whatever its `available_at`: questions about
    what was known at a time go through PointInTimeView.
    """
    for name in (column, group):
        if name not in spec.all_columns:
            raise ValueError(f"{spec.name} has no column {name!r}")
    with connect() as connection:
        rows = connection.execute(
            f"SELECT {group}, max({column}) FROM {table_source(store, spec)} "
            f"GROUP BY {group}"
        ).fetchall()
    return dict(rows)


def write_rows(
    store: Path,
    spec: TableSpec,
    rows: Iterable[Mapping[str, object]],
    *,
    now: datetime | None = None,
) -> WriteResult:
    """Append rows to a table, skipping any it already has, so re-running is safe.

    Each row has the table's columns plus `source`, `source_ref`, `available_at`, and
    `time_assumed`; `write_rows` sets `ingested_at` itself (to `now`, which defaults to
    the current time). Timestamps must be aware datetimes, and a missing value is None.

    A row whose (key, `available_at`) is already stored isn't written again. It counts
    as skipped if its values match, or as a conflict if they don't, and the stored row
    always wins. Two different rows with the same (key, `available_at`) in one call
    raise StoreError. Assumes one writer per table at a time.
    """
    ingested_at = datetime.now(UTC) if now is None else to_utc(now)
    records = [_validated(spec, row, number) for number, row in enumerate(rows, 1)]
    if not records:
        return WriteResult(spec.name, written=0, skipped=0, conflicts=0, path=None)

    given = {c: t for c, t in spec.all_columns.items() if c != "ingested_at"}
    frame = pd.DataFrame(
        {
            column: pd.Series([r[column] for r in records], dtype=_PANDAS_DTYPES[kind])
            for column, kind in given.items()
        }
    )
    select = ", ".join(
        sql_timestamp(ingested_at) + " AS ingested_at"
        if column == "ingested_at"
        else f"CAST({column} AS {kind}) AS {column}"
        for column, kind in spec.all_columns.items()
    )
    identity = [*spec.key, "available_at"]
    order = ", ".join(identity)
    matches = " AND ".join(f"b.{c} = s.{c}" for c in identity)
    same = " AND ".join(
        f"b.{c} IS NOT DISTINCT FROM s.{c}"
        for c in [*spec.columns, "time_assumed"]
        if c not in spec.key
    )
    stored = table_source(store, spec)

    with connect() as connection:
        connection.register("frame", frame)
        # DISTINCT collapses exact duplicates within the batch.
        connection.execute(
            f"CREATE TEMP TABLE batch AS SELECT DISTINCT {select} FROM frame"
        )

        duplicated = connection.execute(
            f"SELECT {order} FROM batch GROUP BY {order} HAVING count(*) > 1 LIMIT 3"
        ).fetchall()
        if duplicated:
            raise StoreError(
                f"{spec.name}: different rows share a key and available_at, "
                f"for example {duplicated}"
            )

        skipped, conflicts = connection.execute(
            f"SELECT count(*) FILTER (WHERE {same}), count(*) FILTER (WHERE NOT ({same})) "
            f"FROM batch b JOIN {stored} s ON {matches}"
        ).fetchone() or (0, 0)
        if conflicts:
            examples = connection.execute(
                f"SELECT {', '.join('b.' + c for c in identity)} FROM batch b "
                f"JOIN {stored} s ON {matches} WHERE NOT ({same}) LIMIT 3"
            ).fetchall()
            logger.warning(
                "%s: kept %d stored rows that differ from new ones with the same key "
                "and available_at, for example %s",
                spec.name,
                conflicts,
                examples,
            )

        connection.execute(
            f"CREATE TEMP TABLE new_rows AS SELECT * FROM batch b "
            f"WHERE NOT EXISTS (SELECT 1 FROM {stored} s WHERE {matches})"
        )
        (written,) = connection.execute("SELECT count(*) FROM new_rows").fetchone() or (
            0,
        )
        if not written:
            return WriteResult(spec.name, 0, skipped, conflicts, path=None)

        # Write under a hidden name, then rename, so readers never see half a file.
        directory = store / spec.name
        directory.mkdir(parents=True, exist_ok=True)
        name = f"part-{ingested_at:%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:8]}.parquet"
        path, partial = directory / name, directory / f".{name}.tmp"
        try:
            connection.execute(
                f"COPY (SELECT * FROM new_rows ORDER BY {order}) "
                f"TO {sql_string(str(partial))} (FORMAT parquet, COMPRESSION zstd)"
            )
            partial.replace(path)
        finally:
            partial.unlink(missing_ok=True)

    return WriteResult(spec.name, written, skipped, conflicts, path)


def _validated(
    spec: TableSpec, row: Mapping[str, object], number: int
) -> dict[str, object]:
    """Check one row against the table, and return it with timestamps in UTC."""
    where = f"{spec.name} row {number}"
    expected = set(spec.all_columns) - {"ingested_at"}
    if "ingested_at" in row:
        raise StoreError(f"{where}: don't pass ingested_at; write_rows sets it")
    if missing := sorted(expected - set(row)):
        raise StoreError(f"{where}: missing columns {missing}")
    if unexpected := sorted(set(row) - expected):
        raise StoreError(f"{where}: unexpected columns {unexpected}")

    record: dict[str, object] = {}
    for column, kind in spec.all_columns.items():
        if column == "ingested_at":
            continue
        value = row[column]
        if value is None:
            if column in spec.key or column in PROVENANCE_COLUMNS:
                raise StoreError(f"{where}: {column} can't be empty")
        elif kind == "TIMESTAMPTZ" and _is_naive(value):
            raise StoreError(
                f"{where}: {column} is a naive datetime; timestamps must be "
                "timezone-aware (doc/time-model.md, rule 1)"
            )
        elif not _fits(value, kind):
            raise StoreError(f"{where}: {column}={value!r} isn't a valid {kind}")
        elif isinstance(value, datetime):
            value = to_utc(value)
        record[column] = value

    if not record["source"] or not record["source_ref"]:
        raise StoreError(f"{where}: source and source_ref can't be blank")
    return record


def _is_naive(value: object) -> bool:
    return isinstance(value, datetime) and value.utcoffset() is None


def _fits(value: object, kind: str) -> bool:
    """Whether a Python value can be stored in a column of this type."""
    match kind:
        case "VARCHAR":
            return isinstance(value, str)
        case "DATE":
            return isinstance(value, date) and not isinstance(value, datetime)
        case "TIMESTAMPTZ":
            return isinstance(value, datetime) and value.utcoffset() is not None
        case "DOUBLE":
            # NaN is ambiguous: use None for a missing value.
            return (
                isinstance(value, int | float)
                and not isinstance(value, bool)
                and (not math.isnan(value))
            )
        case "BIGINT":
            return isinstance(value, int) and not isinstance(value, bool)
        case "BOOLEAN":
            return isinstance(value, bool)
    return False
