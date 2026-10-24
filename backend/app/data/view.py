"""PointInTimeView: the only way to read the point-in-time store (S3.3).

A view is bound to one knowledge time T and answers only from rows with
`available_at <= T` (doc/time-model.md). It opens its own in-memory DuckDB connection
and defines one SQL view per table with that condition built in, so no query on the
connection can see a later row, even one that forgets to filter. Every read goes
through `_select`, which also re-checks each row and records it in the access log that
feeds a run's audit (S7.7) and the bias checks (E12).

Read functions are methods that call `_select` and return the records in
app/data/records.py:

- `get_macro_as_of` and `get_macro_series_as_of`: macro series as published (S4.4)
- `resolve_ticker`: the security that used a ticker at the time (S5.2)
- `get_price_as_of` and `get_price_history_as_of`: daily bars whose sessions had
  closed (S6.3)
- `get_latest_filing_as_of` and `list_filings_as_of`: filings EDGAR had accepted (S5.4)

Callers use one view per request or backtest decision, and close it when done:

    with PointInTimeView(parse_knowledge_time("2020-06-05")) as view:
        view.get_macro_as_of("UNRATE")  # May 2020's first print, 13.3%
        view.access_log  # what was read, and when each row became known

A view isn't thread-safe: never use one from two threads at once. Handing it from one
thread to the next, as the API's worker threads do within a request, is fine.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Self

from app.config import get_settings
from app.data import calendar
from app.data.errors import LookAheadError, NotFoundError
from app.data.records import Filing, MacroObservation, PriceBar, Security
from app.data.sources.alfred import SERIES, Series
from app.data.sources.edgar import FORM_FAMILIES
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
        latest_where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Read rows from one table: the one path every read takes.

        `where` is a SQL condition with `?` placeholders for `params`; pass values only
        through `params`. With `latest_per_key`, only each key's most recent version
        known at the knowledge time is returned. `latest_where` then filters those
        latest versions, its placeholders following `where`'s in `params`: "the
        security whose ticker is FB now", where `where` would also match a security
        whose ticker was FB once. Rows come back ordered by `order_by` (a SQL ORDER BY
        list), or by key and `available_at`, with datetimes in UTC. Each returned row
        is checked and added to the access log.
        """
        spec = self._tables.get(table)
        if spec is None:
            raise ValueError(f"this view has no table named {table!r}")
        if latest_where is not None and not latest_per_key:
            raise ValueError("latest_where filters latest versions: use latest_per_key")

        sql = f"SELECT * FROM {spec.name} WHERE ({where})"
        if latest_per_key:
            sql += (
                f" QUALIFY row_number() OVER (PARTITION BY {', '.join(spec.key)}"
                " ORDER BY available_at DESC) = 1"
            )
            if latest_where is not None:
                sql += f" AND ({latest_where})"
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

    def get_macro_as_of(
        self, series_id: str, period: date | None = None
    ) -> MacroObservation | None:
        """A macro series as it was published by the knowledge time.

        With `period`, an observation date such as 2020-05-01 for May 2020, it's that
        observation's latest version; without it, the latest observation published so
        far. None if nothing was published yet. On June 5, 2020 at 09:30 ET, UNRATE is
        May's first print, 13.3%; at 08:00 that morning it's April's, 14.7%.

        Raises NotFoundError for a series that isn't in the catalog
        (app/data/sources/alfred_series.toml).
        """
        series = _macro_series(series_id)
        where = "series_id = ?"
        params: list[object] = [series.id]
        if period is not None:
            where += " AND observation_date = ?"
            params.append(period)
        rows = self._select(
            "macro_observations",
            where=where,
            params=params,
            latest_per_key=True,
            order_by="observation_date DESC",
            limit=1,
        )
        return _macro_record(series, rows[0]) if rows else None

    def get_macro_series_as_of(
        self, series_id: str, start: date | None = None, end: date | None = None
    ) -> list[MacroObservation]:
        """A whole macro series as it looked at the knowledge time, oldest first.

        Each observation from `start` through `end` (both optional and inclusive) is at
        its latest version published by then, for charts and signals. Raises
        NotFoundError for a series that isn't in the catalog.
        """
        series = _macro_series(series_id)
        where = "series_id = ?"
        params: list[object] = [series.id]
        if start is not None:
            where += " AND observation_date >= ?"
            params.append(start)
        if end is not None:
            where += " AND observation_date <= ?"
            params.append(end)
        rows = self._select(
            "macro_observations",
            where=where,
            params=params,
            latest_per_key=True,
            order_by="observation_date",
        )
        return [_macro_record(series, row) for row in rows]

    def resolve_ticker(self, ticker: str) -> Security:
        """The security that used `ticker` at the knowledge time, in any case.

        The curated history comes first (app/data/sources/securities.toml): in 2020,
        FB is Facebook (the security `meta`), and WB is Weibo, though in 2005 it was
        Wachovia. A ticker that only SEC's ticker file lists resolves from when the
        newest download of that file known at the knowledge time was made, because the
        file says only who uses a ticker now; the result is flagged `time_assumed`.

        Raises NotFoundError if no security in our data used the ticker then, or if
        SEC's file lists it under more than one company.
        """
        symbol = ticker.strip().upper()
        rows = self._select(
            "securities",
            params=[symbol],
            latest_per_key=True,
            latest_where="ticker = ?",
        )
        if len(rows) > 1:
            # load_curated rejects shared tickers, so the store or the file is broken.
            raise RuntimeError(
                f"securities {[r['security_id'] for r in rows]} all use {symbol} at "
                f"{self.knowledge_time.isoformat()}"
            )
        if rows:
            return _curated_security(rows[0])

        rows = self._select(
            "sec_tickers",
            where="ticker = ? AND available_at = (SELECT max(available_at) FROM sec_tickers)",
            params=[symbol],
        )
        if len(rows) == 1:
            return _sec_security(rows[0])
        raise NotFoundError("ticker", ticker, knowledge_time=self.knowledge_time)

    def get_price_as_of(
        self, ticker: str, session: date | None = None
    ) -> PriceBar | None:
        """A security's latest daily bar whose session had closed by the knowledge time.

        At 09:30 ET on June 5, 2020, AAPL's latest bar is June 4's: June 5's isn't
        known until that session closes at 16:00. With `session`, it's that session's
        bar instead: a session that hadn't closed yet raises LookAheadError, and a day
        without a session raises CalendarError. None if no bar is known, such as before
        the security's first session.

        The ticker is resolved at the knowledge time (see `resolve_ticker`), so FB in
        2020 reads Facebook's bars.
        """
        security = self.resolve_ticker(ticker)
        where = "security_id = ?"
        params: list[object] = [security.security_id]
        if session is not None:
            self._require_known_by(
                calendar.session_close(session),
                f"{security.ticker}'s bar for {session.isoformat()}",
            )
            where += " AND session_date = ?"
            params.append(session)
        rows = self._select(
            "price_bars",
            where=where,
            params=params,
            latest_per_key=True,
            order_by="session_date DESC",
            limit=1,
        )
        return _price_bar(security, rows[0]) if rows else None

    def get_price_history_as_of(self, ticker: str, lookback: int) -> list[PriceBar]:
        """The last `lookback` daily bars known at the knowledge time, oldest first.

        For signals such as momentum: at 09:30 ET on June 5, 2020, a lookback of 3 gives
        AAPL's bars for June 2, 3, and 4. If fewer bars are known, fewer come back, and a
        session without a bar is skipped, not filled. The ticker is resolved as for
        `get_price_as_of`.
        """
        if lookback < 1:
            raise ValueError(f"lookback must be at least 1 session, not {lookback}")
        security = self.resolve_ticker(ticker)
        rows = self._select(
            "price_bars",
            where="security_id = ?",
            params=[security.security_id],
            latest_per_key=True,
            order_by="session_date DESC",
            limit=lookback,
        )
        return [_price_bar(security, row) for row in reversed(rows)]

    def get_latest_filing_as_of(
        self, ticker: str, form: str = "10-Q", include_amendments: bool = False
    ) -> Filing | None:
        """The latest filing of a form that EDGAR had accepted by the knowledge time.

        It counts from the acceptance time, never the period end or the filing date: at
        09:30 ET on June 5, 2020, Apple's latest 10-Q is the one for the quarter ended
        March 28 (accepted at 18:03 ET on April 30), and the next one, accepted on July
        30, isn't visible. `form` is a family, "10-K", "10-Q", or "8-K"; "10-K" also
        covers 10-K405 and 10-KT. Amendments, such as a 10-Q/A, count only with
        `include_amendments`. None if no such filing was accepted yet, as for a fund
        like SPY, which files none.

        The ticker is resolved at the knowledge time (see `resolve_ticker`), and the
        filings of every CIK the security had by then are searched.
        """
        filings = self._filings(ticker, [form], include_amendments, limit=1)
        return filings[0] if filings else None

    def list_filings_as_of(
        self,
        ticker: str,
        forms: Sequence[str] = ("10-K", "10-Q", "8-K"),
        include_amendments: bool = False,
        limit: int = 100,
    ) -> list[Filing]:
        """A security's filings accepted by the knowledge time, newest first.

        The form families and amendments work as in `get_latest_filing_as_of`, and at
        most `limit` filings come back. `forms` can also be one family, such as "10-Q".
        """
        if isinstance(forms, str):
            forms = [forms]
        return self._filings(ticker, forms, include_amendments, limit)

    def _filings(
        self,
        ticker: str,
        forms: Sequence[str],
        include_amendments: bool,
        limit: int,
    ) -> list[Filing]:
        if limit < 1:
            raise ValueError(f"limit must be at least 1, not {limit}")
        members = []
        for family in forms:
            if family.upper() not in FORM_FAMILIES:
                raise ValueError(
                    f"unknown form {family!r}; expected one of "
                    f"{', '.join(FORM_FAMILIES)}"
                )
            members += FORM_FAMILIES[family.upper()]
        if include_amendments:
            members += [f"{form}/A" for form in members]

        security = self.resolve_ticker(ticker)
        versions = self._select(
            "securities", where="security_id = ?", params=[security.security_id]
        )
        ciks = {row["cik"] for row in versions if row["cik"] is not None}
        if not versions and security.cik is not None:
            ciks = {security.cik}  # a ticker only SEC's file knows
        if not ciks:
            return []
        rows = self._select(
            "filings",
            where=(
                f"cik IN ({', '.join('?' * len(ciks))}) "
                f"AND form IN ({', '.join('?' * len(members))})"
            ),
            params=[*sorted(ciks), *members],
            latest_per_key=True,
            order_by="available_at DESC, accession_number DESC",
            limit=limit,
        )
        return [_filing(security, row) for row in rows]

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


def _macro_series(series_id: str) -> Series:
    """A series in the macro catalog. IDs are FRED's, matched in any case."""
    series = SERIES.get(series_id.upper())
    if series is None:
        raise NotFoundError("series", series_id)
    return series


def _curated_security(row: Mapping[str, Any]) -> Security:
    """A `securities` row as a record."""
    return Security(
        security_id=row["security_id"],
        ticker=row["ticker"],
        name=row["name"],
        cik=row["cik"],
        share_class=row["share_class"],
        effective_date=row["effective_date"],
        available_at=row["available_at"],
        time_assumed=row["time_assumed"],
        source=row["source"],
        source_ref=row["source_ref"],
    )


def _sec_security(row: Mapping[str, Any]) -> Security:
    """A `sec_tickers` row as a record. Its ID combines the CIK and the ticker,
    which can't clash with the curated file's lowercase IDs."""
    return Security(
        security_id=f"{row['cik']}-{row['ticker']}",
        ticker=row["ticker"],
        name=row["name"],
        cik=row["cik"],
        share_class=None,
        effective_date=None,
        available_at=row["available_at"],
        time_assumed=row["time_assumed"],
        source=row["source"],
        source_ref=row["source_ref"],
    )


def _filing(security: Security, row: Mapping[str, Any]) -> Filing:
    """A `filings` row as a record, with links to the filing on EDGAR and the
    security's name and ticker at the knowledge time."""
    cik, accession = row["cik"], row["accession_number"]
    folder = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
    )
    document = row["primary_document"]
    return Filing(
        security_id=security.security_id,
        ticker=security.ticker,
        cik=cik,
        company_name=security.name,
        accession_number=accession,
        form=row["form"],
        is_amendment=row["is_amendment"],
        amends=row["amends"],
        period_of_report=row["period_of_report"],
        filing_date=row["filing_date"],
        available_at=row["available_at"],
        time_assumed=row["time_assumed"],
        document_url=f"{folder}/{document}" if document else None,
        index_url=f"{folder}/{accession}-index.htm",
        source=row["source"],
        source_ref=row["source_ref"],
    )


def _price_bar(security: Security, row: Mapping[str, Any]) -> PriceBar:
    """A `price_bars` row as a record, under the ticker and CIK the security had at
    the knowledge time."""
    return PriceBar(
        security_id=security.security_id,
        ticker=security.ticker,
        cik=security.cik,
        session_date=row["session_date"],
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row["volume"],
        available_at=row["available_at"],
        time_assumed=row["time_assumed"],
        source=row["source"],
        source_ref=row["source_ref"],
    )


def _macro_record(series: Series, row: Mapping[str, Any]) -> MacroObservation:
    """A `macro_observations` row as a record, with its series' metadata."""
    return MacroObservation(
        series_id=series.id,
        title=series.title,
        units=series.units,
        frequency=series.frequency,
        seasonal_adjustment=series.seasonal_adjustment,
        release=series.release.name,
        period=row["observation_date"],
        value=row["value"],
        vintage_date=row["vintage_date"],
        available_at=row["available_at"],
        time_assumed=row["time_assumed"],
        source=row["source"],
        source_ref=row["source_ref"],
    )
