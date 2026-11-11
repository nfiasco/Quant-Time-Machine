"""PointInTimeView: the only way to read the point-in-time store (S3.3).

A view is bound to one knowledge time T and answers only from rows with
`available_at <= T` (doc/reference/time-model.md). It opens its own in-memory DuckDB connection
and defines one SQL view per table with that condition built in, so no query on the
connection can see a later row, even one that forgets to filter. Every read of rows goes
through `_select`, which also re-checks each row and records it in the access log that
feeds a run's audit (S7.7) and the bias checks (E12). The catalogs' coverage reads go
through `_spans`, which returns date ranges rather than rows, so they add nothing to the
log.

A view can also be pinned to a data version (S3.7, app/data/versions.py). It then
reads only the files that version lists, and only rows ingested by then, so a saved
run's answers never change when new data arrives. The API pins every request to the
newest data version.

Read functions are methods that call `_select` and return the records in
app/data/records.py:

- `get_macro_as_of` and `get_macro_series_as_of`: macro series as published (S4.4)
- `get_revision_history`: every version of one observation published so far (S4.5)
- `series_coverage`: each catalog series, and how much of it was published (S8.5)
- `resolve_ticker`: the security that used a ticker at the time (S5.2)
- `get_security`: a curated security by its ID, even after it stopped trading (S7.3)
- `get_price_as_of`, `get_price_history_as_of`, and `get_price_series_as_of`: daily
  bars whose sessions had closed (S6.3, S6.4)
- `get_corporate_actions_as_of`: splits and cash dividends by ex-date, known with their
  bars (S6.4)
- `get_latest_filing_as_of` and `list_filings_as_of`: filings EDGAR had accepted (S5.4)
- `universe_as_of`: a universe's members, from their effective dates (S6.5)
- `universe_coverage`: those members, and how far their data reaches (S8.5)
- `get_fundamentals_as_of`: a standard metric's last quarters, from the XBRL facts filed
  by then (S5.7)
- `fundamentals_coverage`: how a standard metric's XBRL concepts cover each universe
  member's filings (S5.6)

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
from app.data import calendar, fundamentals, versions
from app.data.errors import DataVersionError, LookAheadError, NotFoundError
from app.data.records import (
    CompanyCoverage,
    CorporateAction,
    DateRange,
    Filing,
    Fundamental,
    FundamentalsCoverage,
    MacroObservation,
    PriceBar,
    Security,
    SeriesCoverage,
    UniverseMember,
)
from app.data.sources import metrics
from app.data.sources.alfred import SERIES, Series
from app.data.sources.edgar import FORM_FAMILIES
from app.data.sources.universes import UNIVERSES, Universe
from app.data.store import TableSpec, connect, sql_timestamp, store_dir, table_source
from app.data.tables import TABLES
from app.data.timeutil import ET, to_utc

__all__ = [
    "AccessRecord",
    "DataVersionError",
    "LookAheadError",
    "NotFoundError",
    "PointInTimeView",
]


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
        app/data/tables.py. With a `data_version`, the view reads only the files that
        version lists, and only rows ingested by then; a table it doesn't list reads as
        empty. Without one, it reads every file in the store now. Raises
        DataVersionError if the store doesn't have the version, or if any of its files
        is missing or changed.
        """
        self.knowledge_time = to_utc(knowledge_time)
        self.data_version = data_version
        if store is None:
            store = store_dir(get_settings().data_dir)
        self._version = (
            None if data_version is None else versions.open_version(store, data_version)
        )
        self._tables = {
            t.name: t for t in (TABLES.values() if tables is None else tables)
        }
        self._log: list[AccessRecord] = []
        self._connection = connect()
        for spec in self._tables.values():
            files = (
                None if self._version is None else self._version.paths(store, spec.name)
            )
            self._connection.execute(
                f"CREATE VIEW {spec.name} AS SELECT * FROM "
                f"{table_source(store, spec, files)} WHERE {self._row_filter()}"
            )

    def _row_filter(self) -> str:
        """The condition built into every table's view: known by the knowledge time, and,
        when the view is pinned, ingested by its data version."""
        condition = f"available_at <= {sql_timestamp(self.knowledge_time)}"
        if self._version is not None:
            ingested = sql_timestamp(self._version.ingested_through)
            condition += f" AND ingested_at <= {ingested}"
        return condition

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
            self._check_known(table, available_at, row["ingested_at"])
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

    def _spans(
        self,
        table: str,
        column: str,
        *,
        by: str,
        where: str = "true",
        params: Sequence[object] = (),
    ) -> dict[Any, tuple[Any, Any]]:
        """The first and last `column` among each `by` group's rows known by the
        knowledge time, for catalogs, which need how far data reaches, not its rows.

        `where` and `params` work as in `_select`. Like `_select`, it reads only the
        table's view, so it can't see a later row, and it checks each group's newest
        `available_at` and `ingested_at` the way `_select` checks each row. It returns
        no rows, so it adds nothing to the access log. Datetimes come back in UTC.
        """
        spec = self._tables.get(table)
        if spec is None:
            raise ValueError(f"this view has no table named {table!r}")
        # Both names end up in SQL.
        if unknown := sorted({column, by} - set(spec.all_columns)):
            raise ValueError(f"{table} has no columns named {unknown}")

        cursor = self._connection.execute(
            f"SELECT {by}, min({column}), max({column}), max(available_at), "
            f"max(ingested_at) FROM {spec.name} WHERE ({where}) GROUP BY {by}",
            list(params),
        )
        spans: dict[Any, tuple[Any, Any]] = {}
        for group, first, last, available_at, ingested_at in cursor.fetchall():
            self._check_known(table, to_utc(available_at), to_utc(ingested_at))
            spans[group] = (
                to_utc(first) if isinstance(first, datetime) else first,
                to_utc(last) if isinstance(last, datetime) else last,
            )
        return spans

    def _check_known(
        self, table: str, available_at: datetime, ingested_at: datetime
    ) -> None:
        """Raise RuntimeError for a row read after the knowledge time, or ingested
        after the pinned data version. The table views make both impossible, so the
        store or this class is broken."""
        if available_at > self.knowledge_time:
            raise RuntimeError(
                f"{table} returned a row available at {available_at.isoformat()}, "
                f"after the knowledge time {self.knowledge_time.isoformat()}"
            )
        if self._version is not None and ingested_at > self._version.ingested_through:
            raise RuntimeError(
                f"{table} returned a row ingested at {ingested_at.isoformat()}, "
                f"after data version {self.data_version}"
            )

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

    def get_revision_history(
        self, series_id: str, period: date
    ) -> list[MacroObservation]:
        """Every version of one observation published by the knowledge time, oldest
        first, each with its vintage date and release time (S4.5).

        `period` is an observation date, such as 1990-01-01 for January 1990, whose
        unemployment rate was first published as 5.3% on February 2, 1990, and revised
        to 5.4% on March 8, 1996: from then on, both versions are listed. A revision
        published later stays invisible, as in every read. [] if nothing was published
        yet. Raises NotFoundError for a series that isn't in the catalog.
        """
        series = _macro_series(series_id)
        rows = self._select(
            "macro_observations",
            where="series_id = ? AND observation_date = ?",
            params=[series.id, period],
            order_by="available_at",
        )
        return [_macro_record(series, row) for row in rows]

    def series_coverage(self) -> list[SeriesCoverage]:
        """Every series in the macro catalog, in its order, with how much of it was
        published by the knowledge time (S8.5).

        At 09:30 ET on June 5, 2020, UNRATE's observations run through May 2020, whose
        first print came out in that morning's vintage. A series with nothing published
        yet has neither: GDP's archive starts with the vintage of December 4, 1991.
        """
        periods = self._spans("macro_observations", "observation_date", by="series_id")
        vintages = self._spans("macro_observations", "vintage_date", by="series_id")
        return [
            SeriesCoverage(
                series_id=series.id,
                title=series.title,
                units=series.units,
                frequency=series.frequency,
                seasonal_adjustment=series.seasonal_adjustment,
                release=series.release.name,
                observations=_date_range(periods.get(series.id)),
                vintages=_date_range(vintages.get(series.id)),
            )
            for series in SERIES.values()
        ]

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

    def get_security(self, security_id: str) -> Security:
        """A curated security, by its ID, as identified at the knowledge time (S7.3).

        Its ticker, name, and CIK are the ones that applied then, as for
        `resolve_ticker`: `meta` is FB in 2020 and META from June 9, 2022. Unlike a
        ticker, the ID still finds a security that had stopped trading, whose ticker is
        then None: Twitter's from October 28, 2022. The backtest engine reads its
        holdings this way (app/backtest/simulation.py).

        Raises NotFoundError if no version of the security was known yet, or for an ID
        only SEC's ticker file knows, which isn't stable.
        """
        rows = self._select(
            "securities",
            where="security_id = ?",
            params=[security_id],
            latest_per_key=True,
        )
        if not rows:
            raise NotFoundError(
                "security", security_id, knowledge_time=self.knowledge_time
            )
        return _curated_security(rows[0])

    def _identify(self, security: str | Security) -> Security:
        """A ticker resolved at the knowledge time, or a `Security` as given."""
        if isinstance(security, Security):
            return security
        return self.resolve_ticker(security)

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

    def get_price_series_as_of(
        self,
        security: str | Security,
        start: date | None = None,
        end: date | None = None,
    ) -> list[PriceBar]:
        """A security's daily bars known at the knowledge time, oldest first.

        Each session from `start` through `end` (both optional and inclusive) whose bar
        was known by then, for total returns (app/backtest/returns.py). A session
        without a bar is skipped, not filled.

        `security` is a ticker, resolved as for `get_price_as_of`, so FB in 2020 reads
        Facebook's whole history. Or it's a `Security` this view gave, from
        `get_security` or `resolve_ticker`, whose bars are read by its ID: a holding's
        bars can still be read after its ticker changed or it stopped trading.
        """
        security = self._identify(security)
        where = "security_id = ?"
        params: list[object] = [security.security_id]
        if start is not None:
            where += " AND session_date >= ?"
            params.append(start)
        if end is not None:
            where += " AND session_date <= ?"
            params.append(end)
        rows = self._select(
            "price_bars",
            where=where,
            params=params,
            latest_per_key=True,
            order_by="session_date",
        )
        return [_price_bar(security, row) for row in rows]

    def get_corporate_actions_as_of(
        self,
        security: str | Security,
        start: date | None = None,
        end: date | None = None,
    ) -> list[CorporateAction]:
        """A security's splits and cash dividends known at the knowledge time, oldest
        first.

        Ex-dates run from `start` through `end` (both optional and inclusive). Each
        action came with its ex-date's bar, so it's known at that session's close: at
        15:59 ET on August 31, 2020, Apple's 4-for-1 split that day isn't known yet.
        Split factors are the vendor's, such as 7.000007; total returns round them
        (app/backtest/returns.py). `security` is a ticker or a `Security`, as for
        `get_price_series_as_of`.
        """
        security = self._identify(security)
        where = "security_id = ?"
        params: list[object] = [security.security_id]
        if start is not None:
            where += " AND ex_date >= ?"
            params.append(start)
        if end is not None:
            where += " AND ex_date <= ?"
            params.append(end)
        rows = self._select(
            "corporate_actions",
            where=where,
            params=params,
            latest_per_key=True,
            order_by="ex_date, action",
        )
        return [_corporate_action(security, row) for row in rows]

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
        ciks = self._ciks(security.security_id, security.cik)
        if not ciks:
            return []
        rows = self._select(
            "filings",
            where=(
                f"cik IN ({', '.join('?' * len(ciks))}) "
                f"AND form IN ({', '.join('?' * len(members))})"
            ),
            params=[*ciks, *members],
            latest_per_key=True,
            order_by="available_at DESC, accession_number DESC",
            limit=limit,
        )
        return [_filing(security, row) for row in rows]

    def _ciks(self, security_id: str, cik: int | None = None) -> list[int]:
        """Every CIK a security had by the knowledge time, such as Google Inc.'s and
        then Alphabet's for GOOGL. A ticker only SEC's file knows has no curated
        history, so its own `cik` stands in."""
        versions = self._select(
            "securities", where="security_id = ?", params=[security_id]
        )
        ciks = {row["cik"] for row in versions if row["cik"] is not None}
        if not versions and cik is not None:
            ciks = {cik}
        return sorted(ciks)

    def universe_as_of(self, name: str) -> list[UniverseMember]:
        """A universe's members at the knowledge time, by security ID.

        A company is a member from 00:00 ET on the day it joined until the day it left
        (doc/reference/time-model.md, rule 8). `starter_large_caps` leaves out Tesla on December
        1, 2020, because Tesla joined the S&P 500 on December 21, and includes it on
        January 4, 2021. Before 2010 it's empty (D3). Each member comes with its ticker,
        name, and CIK at the knowledge time; the ticker is None if the security had
        stopped trading but hadn't left yet.

        Raises NotFoundError for a universe that isn't in
        app/data/sources/universes.toml.
        """
        universe = _universe(name)
        spells = self._select(
            "universe_members",
            where="universe = ?",
            params=[universe.name],
            latest_per_key=True,
            latest_where="removed IS NULL",
            order_by="security_id",
        )
        if not spells:
            return []
        ids = [row["security_id"] for row in spells]
        identities = {
            row["security_id"]: row
            for row in self._select(
                "securities",
                where=f"security_id IN ({', '.join('?' * len(ids))})",
                params=ids,
                latest_per_key=True,
            )
        }
        if missing := sorted(set(ids) - set(identities)):
            # Ingestion writes identity with membership, so the store is broken.
            raise RuntimeError(
                f"{universe.name} members {missing} have no curated identity at "
                f"{self.knowledge_time.isoformat()}"
            )
        return [
            _universe_member(spell, identities[spell["security_id"]])
            for spell in spells
        ]

    def universe_coverage(self, name: str) -> list[CompanyCoverage]:
        """A universe's members at the knowledge time, as `universe_as_of` gives them,
        each with how far its prices, filings, and XBRL facts reach by then (S8.5).

        Filings and facts count across every CIK the security had by then, such as
        Google Inc.'s and then Alphabet's, and are dated by the New York day EDGAR
        accepted them. Raises NotFoundError for a universe that isn't in
        app/data/sources/universes.toml.
        """
        members = self.universe_as_of(name)
        if not members:
            return []
        ids = [member.security_id for member in members]
        in_ids = f"security_id IN ({', '.join('?' * len(ids))})"
        ciks: dict[str, set[int]] = {security_id: set() for security_id in ids}
        for row in self._select("securities", where=in_ids, params=ids):
            if row["cik"] is not None:
                ciks[row["security_id"]].add(row["cik"])

        prices = self._spans(
            "price_bars", "session_date", by="security_id", where=in_ids, params=ids
        )
        filings: dict[Any, tuple[Any, Any]] = {}
        facts: dict[Any, tuple[Any, Any]] = {}
        if every_cik := sorted(set().union(*ciks.values())):
            in_ciks = f"cik IN ({', '.join('?' * len(every_cik))})"
            filings = self._spans(
                "filings", "available_at", by="cik", where=in_ciks, params=every_cik
            )
            facts = self._spans(
                "xbrl_facts", "available_at", by="cik", where=in_ciks, params=every_cik
            )
        return [
            CompanyCoverage(
                universe=member.universe,
                security_id=member.security_id,
                ticker=member.ticker,
                name=member.name,
                cik=member.cik,
                added=member.added,
                prices=_date_range(prices.get(member.security_id)),
                filings=_new_york_days(filings, ciks[member.security_id]),
                fundamentals=_new_york_days(facts, ciks[member.security_id]),
            )
            for member in members
        ]

    def get_fundamentals_as_of(
        self, ticker: str, metric: str, quarters: int = 8
    ) -> list[Fundamental]:
        """A standard metric's last `quarters` quarters as known at the knowledge time,
        oldest first.

        `metric` is a name in app/data/sources/metrics.toml, such as "revenue". Each
        quarter's value is the latest one filed by then (doc/reference/time-model.md, rule 6). At
        09:30 ET on June 5, 2020, Apple's revenue for the quarter ended March 28, 2020
        is $58,313 million from its 10-Q; the 10-K and the next year's 10-Q that repeat
        it came later. A quarter no filing reported is derived from two year-to-date
        totals known by then: Apple's fourth quarter of fiscal 2021 is the full year
        minus the first nine months, and cites both filings. A quarter without a value
        is skipped, not filled. For an instant metric, such as total assets, the last
        dates come back instead.

        The ticker is resolved at the knowledge time (see `resolve_ticker`), and the
        facts of every CIK the security had by then are read. [] if none were filed
        yet, as for a fund like SPY. Raises ValueError for an unknown metric or fewer
        than one quarter.
        """
        if quarters < 1:
            raise ValueError(f"quarters must be at least 1, not {quarters}")
        standard = metrics.metric(metric)
        security = self.resolve_ticker(ticker)
        ciks = self._ciks(security.security_id, security.cik)
        if not ciks:
            return []
        concepts = standard.concepts_for(security.security_id)
        names = standard.parts_for(security.security_id)
        rows = self._select(
            "xbrl_facts",
            where=(
                f"cik IN ({', '.join('?' * len(ciks))}) AND unit = ? "
                f"AND concept IN ({', '.join('?' * len(names))})"
            ),
            params=[*ciks, standard.unit, *names],
        )
        found = fundamentals.quarterly_values(rows, standard, concepts)
        return [_fundamental(security, standard, q) for q in found[-quarters:]]

    def fundamentals_coverage(
        self, universe: str, metric: str
    ) -> list[FundamentalsCoverage]:
        """How a standard metric's concepts cover the 10-Qs and 10-Ks of every company
        that was in a universe by the knowledge time, those that left included (S5.6).

        For each company, by security ID: its original 10-Qs and 10-Ks from its first
        XBRL fact on, the concept each one reported the metric through, and the periods
        none of the concepts covered, which an override in app/data/sources/metrics.toml
        may fix. Raises NotFoundError for an unknown universe and ValueError for an
        unknown metric.
        """
        name = _universe(universe).name
        standard = metrics.metric(metric)
        spells = self._select("universe_members", where="universe = ?", params=[name])
        return [
            self._coverage(security_id, standard)
            for security_id in sorted({spell["security_id"] for spell in spells})
        ]

    def _coverage(
        self, security_id: str, standard: metrics.Metric
    ) -> FundamentalsCoverage:
        identity = self._select(
            "securities",
            where="security_id = ?",
            params=[security_id],
            latest_per_key=True,
        )
        concepts = standard.concepts_for(security_id)
        names = standard.parts_for(security_id)
        ciks = self._ciks(security_id)
        found = fundamentals.Coverage(0, (), (), ())
        if ciks:
            in_ciks = f"cik IN ({', '.join('?' * len(ciks))})"
            forms = [*FORM_FAMILIES["10-K"], *FORM_FAMILIES["10-Q"]]
            first = self._select(
                "xbrl_facts",
                where=in_ciks,
                params=ciks,
                order_by="available_at",
                limit=1,
            )
            filings = self._select(
                "filings",
                where=f"{in_ciks} AND form IN ({', '.join('?' * len(forms))})",
                params=[*ciks, *forms],
            )
            facts = self._select(
                "xbrl_facts",
                where=(
                    f"{in_ciks} AND unit = ? "
                    f"AND concept IN ({', '.join('?' * len(names))})"
                ),
                params=[*ciks, standard.unit, *names],
            )
            found = fundamentals.coverage(
                filings,
                facts,
                standard,
                concepts,
                since=first[0]["available_at"] if first else None,
            )
        return FundamentalsCoverage(
            security_id=security_id,
            name=identity[0]["name"] if identity else security_id,
            metric=standard.name,
            concepts=concepts,
            filings_checked=found.filings_checked,
            concepts_used=found.concepts_used,
            missing=found.missing,
            ambiguous=found.ambiguous,
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


def _date_range(span: tuple[date, date] | None) -> DateRange | None:
    """A `_spans` entry of dates as a record."""
    return None if span is None else DateRange(*span)


def _new_york_days(
    spans: Mapping[Any, tuple[datetime, datetime]], keys: Iterable[Any]
) -> DateRange | None:
    """The New York days of the earliest and latest instants among the `spans` of some
    keys, such as a security's CIKs; None if none of them has any."""
    found = [spans[key] for key in keys if key in spans]
    if not found:
        return None
    return DateRange(
        min(first for first, _ in found).astimezone(ET).date(),
        max(last for _, last in found).astimezone(ET).date(),
    )


def _macro_series(series_id: str) -> Series:
    """A series in the macro catalog. IDs are FRED's, matched in any case."""
    series = SERIES.get(series_id.upper())
    if series is None:
        raise NotFoundError("series", series_id)
    return series


def _universe(name: str) -> Universe:
    """A universe in the curated file. Names are matched in any case."""
    universe = UNIVERSES.by_name.get(name.strip().lower())
    if universe is None:
        raise NotFoundError("universe", name)
    return universe


def _universe_member(
    spell: Mapping[str, Any], identity: Mapping[str, Any]
) -> UniverseMember:
    """A `universe_members` row as a record, with the security's ticker, name, and CIK
    at the knowledge time."""
    return UniverseMember(
        universe=spell["universe"],
        security_id=spell["security_id"],
        ticker=identity["ticker"],
        name=identity["name"],
        cik=identity["cik"],
        added=spell["added"],
        available_at=spell["available_at"],
        time_assumed=spell["time_assumed"],
        source=spell["source"],
        source_ref=spell["source_ref"],
    )


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


def _fundamental(
    security: Security, metric: metrics.Metric, quarter: fundamentals.Quarter
) -> Fundamental:
    """A quarter as a record, under the ticker and CIK the security had at the
    knowledge time."""
    return Fundamental(
        security_id=security.security_id,
        ticker=security.ticker,
        cik=security.cik,
        metric=metric.name,
        concept=quarter.concept,
        unit=metric.unit,
        period_start=quarter.period_start,
        period_end=quarter.period_end,
        fiscal_year=quarter.fiscal_year,
        fiscal_period=quarter.fiscal_period,
        value=quarter.value,
        derived=quarter.derived,
        accession_numbers=quarter.accession_numbers,
        available_at=quarter.available_at,
        time_assumed=quarter.time_assumed,
        source="edgar",
        source_ref=quarter.source_ref,
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


def _corporate_action(security: Security, row: Mapping[str, Any]) -> CorporateAction:
    """A `corporate_actions` row as a record, under the ticker and CIK the security had
    at the knowledge time."""
    return CorporateAction(
        security_id=security.security_id,
        ticker=security.ticker,
        cik=security.cik,
        ex_date=row["ex_date"],
        action=row["action"],
        value=row["value"],
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
