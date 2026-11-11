"""A small made-up market in a temporary store, for engine tests (S7.3, S7.4).

Every price is invented, as in tests/fixtures/: Tiingo's terms don't allow sharing its
data. A spec's universe must be one that app/data/sources/universes.toml names, so the
toy securities are members of `starter_large_caps` in a store that holds nothing else.

    add_security(store, "alpha", "AAA", cik=1)
    add_member(store, "alpha")
    add_bars(store, "alpha", steps(date(2021, 1, 4), date(2021, 4, 30), {...}))
    add_revenue(store, 1, {date(2020, 9, 30): 100.0, date(2020, 12, 31): 110.0})
    add_release(store, "UNRATE", date(2020, 5, 1), 13.3, vintage=date(2020, 6, 5))

Each row becomes known as ingestion would make it known: a security's identity and a
membership at 00:00 ET on their dates, a bar or an action at its session's close, a
revenue fact at its filing's acceptance, and a macro observation at its release's time
on its vintage date (doc/reference/time-model.md, rules 4 to 8). Only poisoned-future
tests move a bar or an action, with `known_at`, to a time after the one it describes.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from app.data import calendar
from app.data.sources.alfred import SERIES, vintage_known_at
from app.data.store import write_rows
from app.data.tables import (
    CORPORATE_ACTIONS,
    MACRO_OBSERVATIONS,
    PRICE_BARS,
    SECURITIES,
    UNIVERSE_MEMBERS,
    XBRL_FACTS,
)
from app.data.timeutil import market_time

UNIVERSE = "starter_large_caps"

INGESTED_AT = datetime(2026, 10, 19, 12, tzinfo=UTC)
"""When the toy rows count as ingested, as for the fixtures."""

Price = float | tuple[float, float]
"""A session's close, which is also its open, or its (open, close)."""


def add_security(
    store: Path,
    security_id: str,
    ticker: str,
    *,
    listed: date = date(2005, 1, 3),
    stopped: date | None = None,
    cik: int | None = None,
) -> None:
    """A security with `ticker` from `listed`. From `stopped`, the first day it didn't
    trade, it has no ticker, as when Twitter stopped trading. A `cik` lets reads find
    its XBRL facts (`add_revenue`)."""
    changes = [(listed, ticker)] + ([] if stopped is None else [(stopped, None)])
    write_rows(
        store,
        SECURITIES,
        [
            {
                "security_id": security_id,
                "ticker": symbol,
                "name": f"{ticker} Corp.",
                "cik": cik,
                "share_class": "Common stock",
                "effective_date": day,
                "source": "test",
                "source_ref": f"made up: {ticker} from {day}",
                "available_at": market_time(day, time(0)),
                "time_assumed": False,
            }
            for day, symbol in changes
        ],
        now=INGESTED_AT,
    )


def add_member(
    store: Path,
    security_id: str,
    *,
    added: date = date(2010, 1, 1),
    removed: date | None = None,
) -> None:
    """A membership of `starter_large_caps` from `added`, and its end on `removed`,
    known only from that day, as a second version of the spell."""
    spell = {
        "universe": UNIVERSE,
        "security_id": security_id,
        "added": added,
        "removed": None,
        "source": "test",
        "source_ref": f"made up: {security_id} joins",
        "available_at": market_time(added, time(0)),
        "time_assumed": False,
    }
    rows = [spell]
    if removed is not None:
        rows.append(
            spell
            | {
                "removed": removed,
                "source_ref": f"made up: {security_id} leaves",
                "available_at": market_time(removed, time(0)),
            }
        )
    write_rows(store, UNIVERSE_MEMBERS, rows, now=INGESTED_AT)


def add_bars(
    store: Path,
    security_id: str,
    prices: Mapping[date, Price],
    *,
    volume: int = 1000,
    known_at: datetime | None = None,
) -> None:
    """A daily bar for each session in `prices`, known at that session's close, or at
    `known_at`, which poisoned-future tests set to make a later version of a bar. A
    `volume` of 0 makes bars for sessions in which nothing traded, as Tiingo has for
    the day a delisted company's trading was suspended."""
    rows = []
    for day, price in sorted(prices.items()):
        opened, closed = price if isinstance(price, tuple) else (price, price)
        rows.append(
            {
                "security_id": security_id,
                "session_date": day,
                "open": opened,
                "high": max(opened, closed),
                "low": min(opened, closed),
                "close": closed,
                "volume": volume,
                "source": "test",
                "source_ref": f"made up: {security_id} {day}",
                "available_at": known_at or calendar.session_close(day),
                "time_assumed": False,
            }
        )
    write_rows(store, PRICE_BARS, rows, now=INGESTED_AT)


def add_action(
    store: Path,
    security_id: str,
    ex_date: date,
    action: str,
    value: float,
    *,
    known_at: datetime | None = None,
) -> None:
    """A split (`value` new shares per old one) or a cash dividend (`value` per
    share), known at its ex-date's close, or at `known_at`, as for `add_bars`."""
    write_rows(
        store,
        CORPORATE_ACTIONS,
        [
            {
                "security_id": security_id,
                "ex_date": ex_date,
                "action": action,
                "value": value,
                "source": "test",
                "source_ref": f"made up: {security_id} {action} on {ex_date}",
                "available_at": known_at or calendar.session_close(ex_date),
                "time_assumed": False,
            }
        ],
        now=INGESTED_AT,
    )


def steps(start: date, end: date, levels: Mapping[date, float]) -> dict[date, float]:
    """A close for every session from `start` through `end`: each of `levels` holds
    from its date until the next one's. The first must be on or before `start`."""
    if min(levels) > start:
        raise ValueError(f"no level for {start}")
    prices = {}
    for day in calendar.sessions_between(start, end):
        prices[day] = levels[max(d for d in levels if d <= day)]
    return prices


def add_fact(
    store: Path,
    cik: int,
    start: date,
    end: date,
    value: float,
    *,
    accepted: datetime,
    form: str = "10-Q",
    accession: str | None = None,
) -> None:
    """Revenue from `start` through `end`, as a filing EDGAR accepted at `accepted`
    reported it: known from then (doc/reference/time-model.md, rule 6). A quarter, or
    a year-to-date total from which reads derive a quarter no filing reported."""
    accession = accession or f"toy-{cik}-{form}-{end}-{accepted:%Y%m%dT%H%M%S}"
    write_rows(
        store,
        XBRL_FACTS,
        [
            {
                "cik": cik,
                "accession_number": accession,
                "concept": "us-gaap:Revenues",
                "unit": "USD",
                "period_start": start,
                "period_end": end,
                "duration_days": (end - start).days + 1,
                "value": value,
                "fiscal_year": None,
                "fiscal_period": None,
                "form": form,
                "filed": accepted.date(),
                "source": "test",
                "source_ref": accession,
                "available_at": accepted,
                "time_assumed": False,
            }
        ],
        now=INGESTED_AT,
    )


def add_revenue(
    store: Path,
    cik: int,
    quarters: Mapping[date, float],
    *,
    filed_after: timedelta = timedelta(days=40),
) -> None:
    """Each calendar quarter's revenue in `quarters`, by the quarter's last day, in a
    10-Q that EDGAR accepted at 16:30 ET `filed_after` its end."""
    for end, value in quarters.items():
        if end.month % 3 or (end + timedelta(days=1)).day != 1:
            raise ValueError(f"{end} doesn't end a calendar quarter")
        accepted = market_time(end + filed_after, time(16, 30))
        add_fact(
            store, cik, date(end.year, end.month - 2, 1), end, value, accepted=accepted
        )


def add_release(
    store: Path, series_id: str, period: date, value: float | None, vintage: date
) -> None:
    """A version of a macro observation, `period`'s `value` as ALFRED's vintage of
    `vintage` gave it: known at its release's time that day, as ingestion times it (None
    for a value published as missing)."""
    known, assumed = vintage_known_at(SERIES[series_id].release, vintage)
    write_rows(
        store,
        MACRO_OBSERVATIONS,
        [
            {
                "series_id": series_id,
                "observation_date": period,
                "value": value,
                "vintage_date": vintage,
                "source": "test",
                "source_ref": f"made up: {series_id} {period} from {vintage}",
                "available_at": known,
                "time_assumed": assumed,
            }
        ],
        now=INGESTED_AT,
    )
