"""PointInTimeView: the only way to read the point-in-time store (S3.3).

A view is bound to one knowledge time T and answers only from rows with
`available_at <= T` (doc/time-model.md). It opens its own in-memory DuckDB connection
and defines one SQL view per table with that condition built in, so no query on the
connection can see a later row, even one that forgets to filter. Every read goes
through `_select`, which also re-checks each row and records it in the access log that
feeds a run's audit (S7.7) and the bias checks (E12).

Read functions (tasks 11, 13, and 16) are methods that call `_select`. For example:

    def get_macro_as_of(self, series_id: str) -> dict[str, object] | None:
        rows = self._select(
            "macro_observations",
            where="series_id = ?",
            params=[series_id],
            latest_per_key=True,
            order_by="observation_date DESC",
            limit=1,
        )
        return rows[0] if rows else None

Callers use one view per request or backtest decision, and close it when done:

    with PointInTimeView(parse_knowledge_time("2020-06-05")) as view:
        view.get_macro_as_of("UNRATE")  # May 2020's first print, 13.3%
        view.access_log  # what was read, and when each row became known

A view isn't thread-safe; don't share one between threads.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self

from app.config import get_settings
from app.data.errors import LookAheadError, NotFoundError
from app.data.store import TableSpec, connect, sql_timestamp, store_dir, table_source
from app.data.tables import TABLES
from app.data.timeutil import to_utc

__all__ = ["AccessRecord", "LookAheadError", "NotFoundError", "PointInTimeView"]


@dataclass(frozen=True)
class AccessRecord:
    """One row a view returned: its table, its key, when it became known, and its source."""

    table: str
    key: tuple[object, ...]
    available_at: datetime
    source_ref: str


class PointInTimeView:
    """Reads the store as it was known at `knowledge_time`."""

    def __init__(
        self,
        knowledge_time: datetime,
        *,
        data_version: str | None = None,
        store: Path | None = None,
        tables: Iterable[TableSpec] | None = None,
    ) -> None:
        """Bind a view to an aware `knowledge_time`.

        `store` defaults to DATA_DIR/store, and `tables` to every table in
        app/data/tables.py. Pinning a view to a `data_version` arrives with S3.7.
        """
        self.knowledge_time = to_utc(knowledge_time)
        if data_version is not None:
            raise NotImplementedError(
                "pinning a view to a data version arrives in S3.7"
            )
        self.data_version = data_version
        if store is None:
            store = store_dir(get_settings().data_dir)
        self._tables = {
            t.name: t for t in (TABLES.values() if tables is None else tables)
        }
        self._log: list[AccessRecord] = []
        self._connection = connect()
        for spec in self._tables.values():
            self._connection.execute(
                f"CREATE VIEW {spec.name} AS SELECT * FROM {table_source(store, spec)} "
                f"WHERE {self._row_filter()}"
            )

    def _row_filter(self) -> str:
        """The condition built into every table's view.

        S3.7 adds `AND ingested_at <= ...` here when the view is pinned to a data version.
        """
        return f"available_at <= {sql_timestamp(self.knowledge_time)}"

    @property
    def access_log(self) -> tuple[AccessRecord, ...]:
        """Every row this view has returned, in the order it returned them."""
        return tuple(self._log)

    def _select(
        self,
        table: str,
        *,
        where: str = "true",
        params: Sequence[object] = (),
        latest_per_key: bool = False,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, object]]:
        """Read rows from one table: the one path every read takes.

        `where` is a SQL condition with `?` placeholders for `params`; pass values only
        through `params`. With `latest_per_key`, only each key's most recent version
        known at the knowledge time is returned. Rows come back ordered by `order_by`
        (a SQL ORDER BY list), or by key and `available_at`, with datetimes in UTC.
        Each returned row is checked and added to the access log.
        """
        spec = self._tables.get(table)
        if spec is None:
            raise ValueError(f"this view has no table named {table!r}")

        sql = f"SELECT * FROM {spec.name} WHERE ({where})"
        if latest_per_key:
            sql += (
                f" QUALIFY row_number() OVER (PARTITION BY {', '.join(spec.key)}"
                " ORDER BY available_at DESC) = 1"
            )
        sql += f" ORDER BY {order_by or ', '.join([*spec.key, 'available_at'])}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"

        cursor = self._connection.execute(sql, list(params))
        names = [column[0] for column in cursor.description]
        rows = []
        for values in cursor.fetchall():
            row = {
                name: to_utc(value) if isinstance(value, datetime) else value
                for name, value in zip(names, values, strict=True)
            }
            available_at = row["available_at"]
            assert isinstance(available_at, datetime)
            if available_at > self.knowledge_time:
                # The table views make this impossible, so the store or this class is broken.
                raise RuntimeError(
                    f"{table} returned a row available at {available_at.isoformat()}, "
                    f"after the knowledge time {self.knowledge_time.isoformat()}"
                )
            self._log.append(
                AccessRecord(
                    table=table,
                    key=tuple(row[column] for column in spec.key),
                    available_at=available_at,
                    source_ref=str(row["source_ref"]),
                )
            )
            rows.append(row)
        return rows

    def _require_known_by(self, moment: datetime, what: str) -> None:
        """Raise LookAheadError if `what` only became known at `moment`, after this view's
        knowledge time.

        Read functions call it when asked for something specific whose availability
        doesn't depend on the data, such as the bar for a session whose close is later.
        """
        moment = to_utc(moment)
        if moment > self.knowledge_time:
            raise LookAheadError(
                f"{what} isn't known until {moment:%Y-%m-%dT%H:%M:%SZ}, after the "
                f"knowledge time {self.knowledge_time:%Y-%m-%dT%H:%M:%SZ}",
                knowledge_time=self.knowledge_time,
                data_version=self.data_version,
            )

    def close(self) -> None:
        """Close the view's DuckDB connection."""
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"PointInTimeView(knowledge_time={self.knowledge_time.isoformat()}, "
            f"data_version={self.data_version!r})"
        )
