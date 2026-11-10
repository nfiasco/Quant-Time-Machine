"""A small made-up market in a temporary store, for engine tests (S7.3).

Every price is invented, as in tests/fixtures/: Tiingo's terms don't allow sharing its
data. A spec's universe must be one that app/data/sources/universes.toml names, so the
toy securities are members of `starter_large_caps` in a store that holds nothing else.

    add_security(store, "alpha", "AAA")
    add_member(store, "alpha")
    add_bars(store, "alpha", steps(date(2021, 1, 4), date(2021, 4, 30), {...}))

Each row becomes known as ingestion would make it known: a security's identity and a
membership at 00:00 ET on their dates, and a bar or an action at its session's close
(doc/reference/time-model.md, rules 4 and 8).
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from pathlib import Path

from app.data import calendar
from app.data.store import write_rows
from app.data.tables import CORPORATE_ACTIONS, PRICE_BARS, SECURITIES, UNIVERSE_MEMBERS
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
) -> None:
    """A security with `ticker` from `listed`. From `stopped`, the first day it didn't
    trade, it has no ticker, as when Twitter stopped trading."""
    changes = [(listed, ticker)] + ([] if stopped is None else [(stopped, None)])
    write_rows(
        store,
        SECURITIES,
        [
            {
                "security_id": security_id,
                "ticker": symbol,
                "name": f"{ticker} Corp.",
                "cik": None,
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
    store: Path, security_id: str, prices: Mapping[date, Price], *, volume: int = 1000
) -> None:
    """A daily bar for each session in `prices`, known at that session's close. A
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
                "available_at": calendar.session_close(day),
                "time_assumed": False,
            }
        )
    write_rows(store, PRICE_BARS, rows, now=INGESTED_AT)


def add_action(
    store: Path, security_id: str, ex_date: date, action: str, value: float
) -> None:
    """A split (`value` new shares per old one) or a cash dividend (`value` per
    share), known at its ex-date's close."""
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
                "available_at": calendar.session_close(ex_date),
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
