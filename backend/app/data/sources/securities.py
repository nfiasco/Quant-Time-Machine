"""Company identity: which security used which ticker, and when (S5.2).

`uv run python -m app.data.ingest sec` writes two tables:

- `securities`, from the curated file securities.toml: one row per change in a
  security's ticker, name, or CIK, known from 00:00 ET on the day it took effect.
- `sec_tickers`, from SEC's ticker file (company_tickers.json): one full snapshot per
  download. The file lists only the tickers in use when it's downloaded, so a snapshot
  is known from that moment, and flagged `time_assumed` (doc/time-model.md, rule 11).

`PointInTimeView.resolve_ticker` reads both: the curated history first, then the
newest snapshot known at the knowledge time. Ingestion warns when a curated security's
current ticker and CIK aren't in SEC's file, which usually means the curated file needs
a new entry.
"""

import logging
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time
from itertools import pairwise
from pathlib import Path
from typing import Any

from app.data.raw_cache import CachedResponse
from app.data.sources import IngestContext
from app.data.store import WriteResult, write_rows
from app.data.tables import SEC_TICKERS, SECURITIES
from app.data.timeutil import market_time

logger = logging.getLogger(__name__)

CURATED_FILE = Path(__file__).with_name("securities.toml")

TICKER_FILE = "https://www.sec.gov/files/company_tickers.json"
"""SEC's list of every company's current tickers and CIKs."""

_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*", re.ASCII)
_TICKER = re.compile(r"[A-Z0-9][A-Z0-9.-]*", re.ASCII)


@dataclass(frozen=True)
class Change:
    """One entry in a security's history: what applied from `effective` on."""

    effective: date
    ticker: str | None
    """None from the day the security was delisted."""
    name: str
    cik: int | None
    source: str


@dataclass(frozen=True)
class CuratedSecurity:
    """A security in the curated file, with its whole history, oldest first."""

    id: str
    share_class: str
    symbols: Mapping[str, str]
    """Each price vendor's code for the security, such as {"tiingo": "META"}."""
    history: tuple[Change, ...]

    @property
    def ciks(self) -> list[int]:
        """Every CIK the security has had, oldest first."""
        return list(dict.fromkeys(c.cik for c in self.history if c.cik is not None))


@dataclass(frozen=True)
class Curated:
    """The curated file: its securities by ID, and the starter set ingestion loads."""

    securities: Mapping[str, CuratedSecurity]
    starter_set: tuple[CuratedSecurity, ...]


def load_curated(path: Path = CURATED_FILE) -> Curated:
    """Read and check the curated file.

    Raises ValueError for an entry without a source, dates out of order, or two
    securities using the same ticker at the same time.
    """
    with path.open("rb") as file:
        config = tomllib.load(file)
    securities: dict[str, CuratedSecurity] = {}
    for entry in config.get("securities", ()):
        security = _security(entry, path)
        if security.id in securities:
            raise ValueError(f"{path.name}: {security.id} is listed twice")
        securities[security.id] = security
    _check_tickers_are_never_shared(securities.values(), path)

    starter_set = []
    for security_id in config.get("starter_set", ()):
        if security_id not in securities:
            raise ValueError(
                f"{path.name}: the starter set names unknown {security_id}"
            )
        starter_set.append(securities[security_id])
    return Curated(securities, tuple(starter_set))


def _security(entry: Mapping[str, Any], path: Path) -> CuratedSecurity:
    security_id = entry.get("id", "")
    if not _ID.fullmatch(security_id):
        raise ValueError(
            f"{path.name}: {security_id!r} isn't an ID like apple or alphabet-a"
        )
    where = f"{path.name}: {security_id}"
    history: list[Change] = []
    for item in entry.get("history", ()):
        effective = item.get("from")
        if type(effective) is not date:
            raise ValueError(f"{where}: each history entry needs a from date")
        if history and effective <= history[-1].effective:
            raise ValueError(f"{where}: history dates must increase, see {effective}")
        if not str(item.get("source", "")).startswith("https://"):
            raise ValueError(
                f"{where}: the entry from {effective} needs an https source"
            )
        delisted = item.get("delisted", False)
        ticker = item.get("ticker")
        if delisted == (ticker is not None):
            raise ValueError(
                f"{where}: the entry from {effective} needs a ticker or delisted = true"
            )
        if ticker is not None and not _TICKER.fullmatch(ticker):
            raise ValueError(f"{where}: {ticker!r} isn't an uppercase ticker")
        previous = history[-1] if history else None
        name = item.get("name", previous.name if previous else None)
        if not name:
            raise ValueError(f"{where}: the first entry needs a name")
        history.append(
            Change(
                effective=effective,
                ticker=ticker,
                name=name,
                cik=item.get("cik", previous.cik if previous else None),
                source=item["source"],
            )
        )
    if not history:
        raise ValueError(f"{where} needs a history")
    if not entry.get("share_class"):
        raise ValueError(f"{where} needs a share_class")
    return CuratedSecurity(
        id=security_id,
        share_class=entry["share_class"],
        symbols=dict(entry.get("symbols", {})),
        history=tuple(history),
    )


def _check_tickers_are_never_shared(
    securities: Iterable[CuratedSecurity], path: Path
) -> None:
    """Raise ValueError if two securities use one ticker at the same time.

    Each use runs from its entry's date until the next entry's. Sorted by start, an
    overlap always shows up between neighbors, because one security's uses never
    overlap each other.
    """
    uses: dict[str, list[tuple[date, date, str]]] = {}
    for security in securities:
        ends = [c.effective for c in security.history[1:]] + [date.max]
        for change, end in zip(security.history, ends, strict=True):
            if change.ticker is not None:
                uses.setdefault(change.ticker, []).append(
                    (change.effective, end, security.id)
                )
    for ticker, spans in uses.items():
        for (_, end, first), (start, _, second) in pairwise(sorted(spans)):
            if start < end and first != second:
                raise ValueError(
                    f"{path.name}: {first} and {second} both use {ticker} on {start}"
                )


CURATED = load_curated()
"""The curated securities and the starter set."""


def ingest(context: IngestContext) -> None:
    """Load the curated history, then a snapshot of SEC's ticker file."""
    write_curated(context.store)
    response = context.client.get(TICKER_FILE)
    rows = ticker_file_rows(response)
    result = write_rows(context.store, SEC_TICKERS, rows)
    logger.info(
        "SEC's ticker file: %d tickers, %d new, %d already stored",
        len(rows),
        result.written,
        result.skipped,
    )
    check_against_sec(CURATED, rows)


def write_curated(store: Path) -> WriteResult:
    """Write the curated history to the `securities` table, skipping stored rows."""
    result = write_rows(store, SECURITIES, curated_rows(CURATED))
    logger.info(
        "Curated securities: %d new changes, %d already stored",
        result.written,
        result.skipped,
    )
    return result


def curated_rows(curated: Curated) -> list[dict[str, object]]:
    """One `securities` row per change, known from 00:00 ET on its date."""
    return [
        {
            "security_id": security.id,
            "ticker": change.ticker,
            "name": change.name,
            "cik": change.cik,
            "share_class": security.share_class,
            "effective_date": change.effective,
            "source": "curated",
            "source_ref": change.source,
            "available_at": market_time(change.effective, time(0, 0)),
            "time_assumed": False,
        }
        for security in curated.securities.values()
        for change in security.history
    ]


def ticker_file_rows(response: CachedResponse) -> list[dict[str, object]]:
    """One `sec_tickers` row per ticker in a download of SEC's ticker file.

    The file says only that a company uses a ticker now, so every row is known from the
    download's time, flagged as assumed.
    """
    fetched = f"{TICKER_FILE} fetched {response.fetched_at:%Y-%m-%dT%H:%M:%SZ}"
    rows: dict[tuple[int, str], dict[str, object]] = {}
    for entry in response.json().values():
        key = (int(entry["cik_str"]), entry["ticker"].upper())
        rows.setdefault(
            key,
            {
                "cik": key[0],
                "ticker": key[1],
                "name": entry["title"],
                "source": "edgar",
                "source_ref": fetched,
                "available_at": response.fetched_at,
                "time_assumed": True,
            },
        )
    return list(rows.values())


def check_against_sec(
    curated: Curated, sec_rows: Sequence[Mapping[str, object]]
) -> None:
    """Warn about curated securities whose current ticker SEC's file doesn't list
    under the same CIK. Delisted securities are skipped."""
    listed = {(row["cik"], row["ticker"]) for row in sec_rows}
    for security in curated.securities.values():
        current = security.history[-1]
        if current.ticker is not None and (current.cik, current.ticker) not in listed:
            logger.warning(
                "%s: %s says it trades as %s under CIK %s, but SEC's ticker file "
                "doesn't list that; it may need a new entry",
                security.id,
                CURATED_FILE.name,
                current.ticker,
                current.cik,
            )
