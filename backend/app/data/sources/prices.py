"""Daily prices from any vendor, stored raw (S6.2).

A vendor is a `PriceSource`: it fetches raw daily bars for a symbol over a range of
dates, and says when its end-of-day data stops changing. Tiingo is the one we use
(decision D2, sources/tiingo.py). Everything else happens here, so a licensed or
CRSP-based source would only implement the fetch:

- **Which bars to ask for.** On a security's first run, from 2005; after that, from
  the session after its last stored bar. The range ends at the last session the vendor
  had settled by `now`, so each bar is fetched once, after the vendor's corrections. A
  security delisted before the range would start isn't asked about again.
- **When a bar became known:** its session's close from the NYSE calendar, 16:00 ET or
  13:00 ET on early-close days (doc/time-model.md, rule 4). A bar dated on a day with
  no session is dropped and logged.
- **Raw prices only.** Bars keep the prices they traded at. Splits and cash dividends
  go to `corporate_actions` by ex-date, exactly as the vendor reports them (S6.4 rounds
  split factors such as 7.000007), so later returns never rely on adjusted prices.
- **Missing sessions.** Sessions inside a fetched range that came back without a bar
  are logged and returned in each security's summary; S6.7 reports coverage.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Protocol

from app.data import calendar
from app.data.sources.securities import CuratedSecurity
from app.data.store import max_per_group, write_rows
from app.data.tables import CORPORATE_ACTIONS, PRICE_BARS
from app.data.timeutil import ET, market_time, to_utc

logger = logging.getLogger(__name__)

HISTORY_START = date(2005, 1, 1)
"""Where a security's first download starts (doc/data-sources.md: daily history back
to 2005)."""


@dataclass(frozen=True)
class SourceBar:
    """One daily bar as a vendor reports it, with raw (as-traded) prices."""

    session_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    dividend: float
    """Cash paid per share, if this session is a dividend's ex-date; otherwise 0."""
    split_factor: float
    """New shares per old share, if a split took effect this session; otherwise 1."""


class PriceSource(Protocol):
    """A vendor of daily prices."""

    name: str
    """Stored as each row's `source`, and the key for the vendor's code in a
    security's `symbols`."""

    settled_by: time
    """When a session's bars stop changing at the vendor, New York time."""

    def fetch_bars(self, symbol: str, start: date, end: date) -> list[SourceBar]:
        """Raw daily bars for `symbol` from `start` through `end`."""
        ...


@dataclass(frozen=True)
class PriceIngest:
    """What `ingest_prices` did for one security."""

    security_id: str
    window: tuple[date, date] | None
    """The sessions requested, or None if nothing was."""
    bars: int = 0
    """New bars stored."""
    actions: int = 0
    """New splits and dividends stored."""
    missing_sessions: tuple[date, ...] = ()
    """Sessions in the fetched range that came back without a bar."""
    note: str = ""
    """Why nothing was requested, when nothing was."""


def ingest_prices(
    store: Path,
    source: PriceSource,
    securities: Iterable[CuratedSecurity],
    *,
    now: datetime,
    history_start: date = HISTORY_START,
) -> list[PriceIngest]:
    """Download each security's new bars from `source` and store them.

    Writes one batch per security, so a run stopped by a rate limit keeps what it got,
    and the next run starts after the last stored bar.
    """
    end = last_settled_session(now, source.settled_by)
    last_stored = max_per_group(store, PRICE_BARS, "session_date", group="security_id")
    results = []
    for security in securities:
        result = _ingest_one(
            store, source, security, last_stored.get(security.id), end, history_start
        )
        results.append(result)
        if result.window is None:
            logger.info("%s: nothing requested: %s", security.id, result.note)
            continue
        logger.info(
            "%s: %d new bars and %d corporate actions for %s to %s",
            security.id,
            result.bars,
            result.actions,
            *result.window,
        )
        if missing := result.missing_sessions:
            more = f", and {len(missing) - 5} more" if len(missing) > 5 else ""
            logger.warning(
                "%s: no bar for these sessions: %s%s",
                security.id,
                ", ".join(day.isoformat() for day in missing[:5]),
                more,
            )
    return results


def last_settled_session(now: datetime, settled_by: time) -> date:
    """The latest session whose bars had settled at the vendor by `now`."""
    now = to_utc(now)
    today = now.astimezone(ET).date()
    if calendar.is_session(today) and now >= market_time(today, settled_by):
        return today
    return calendar.previous_session(today)


def _ingest_one(
    store: Path,
    source: PriceSource,
    security: CuratedSecurity,
    last: date | None,
    end: date,
    history_start: date,
) -> PriceIngest:
    symbol = security.symbols.get(source.name)
    if symbol is None:
        return PriceIngest(security.id, None, note=f"no {source.name} symbol")
    start = history_start if last is None else calendar.next_session(last)
    latest = security.history[-1]
    if latest.ticker is None and start >= latest.effective:
        return PriceIngest(security.id, None, note=f"delisted on {latest.effective}")
    if start > end:
        return PriceIngest(security.id, None, note=f"up to date through {last}")

    bars: list[SourceBar] = []
    dropped: list[SourceBar] = []
    for bar in source.fetch_bars(symbol, start, end):
        if start <= bar.session_date <= end and calendar.is_session(bar.session_date):
            bars.append(bar)
        else:
            dropped.append(bar)
    if dropped:
        logger.warning(
            "%s: dropped %d bars dated outside %s to %s or on days without a "
            "session, such as %s",
            security.id,
            len(dropped),
            start,
            end,
            dropped[0].session_date,
        )

    bar_rows: list[dict[str, object]] = []
    action_rows: list[dict[str, object]] = []
    for bar in bars:
        # A bar and the splits and dividends it reports are known at its close.
        provenance = {
            "source": source.name,
            "source_ref": f"{source.name} {symbol} {bar.session_date.isoformat()}",
            "available_at": calendar.session_close(bar.session_date),
            "time_assumed": False,
        }
        bar_rows.append(
            {
                "security_id": security.id,
                "session_date": bar.session_date,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                **provenance,
            }
        )
        actions = []
        if bar.dividend:
            actions.append(("dividend", bar.dividend))
        if bar.split_factor != 1:
            actions.append(("split", bar.split_factor))
        for action, value in actions:
            action_rows.append(
                {
                    "security_id": security.id,
                    "ex_date": bar.session_date,
                    "action": action,
                    "value": value,
                    **provenance,
                }
            )
    bars_written = write_rows(store, PRICE_BARS, bar_rows).written
    actions_written = write_rows(store, CORPORATE_ACTIONS, action_rows).written

    fetched = {bar.session_date for bar in bars}
    missing: list[date] = []
    if fetched:
        # On a first run the history starts at the first bar; later, at `start`.
        first = start if last is not None else min(fetched)
        missing = [
            session
            for session in calendar.sessions_between(first, max(fetched))
            if session not in fetched
        ]
    return PriceIngest(
        security.id, (start, end), bars_written, actions_written, tuple(missing)
    )
