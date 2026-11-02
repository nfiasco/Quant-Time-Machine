"""Total returns against Tiingo's adjusted closes, from the local data (S6.4).

Tiingo's terms don't allow committing its data (D2), so this test reads the local raw
cache and store, which CI doesn't have. It's marked `local_data` and skipped by
default: run it with `uv run pytest -m local_data` after `ingest tiingo`.

Each cached response carries the adjusted closes we never store. Their scale is set by
the splits and dividends known when the response was fetched, so a return is compared
only between two sessions of the same response.
"""

import json
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.backtest.returns import monthly_total_returns, total_returns_as_of
from app.config import get_settings
from app.data.sources import universes
from app.data.sources.securities import CuratedSecurity
from app.data.store import store_dir
from app.data.versions import latest_data_version
from app.data.view import PointInTimeView

pytestmark = pytest.mark.local_data

TOLERANCE = 1e-5
"""Rounding a split factor moves its day by up to about 1e-6 (Apple's 7.000007 in
2014); every other day agrees to about 1e-11."""

LISTED = [
    security
    for security in universes.ingest_set()
    if security.history[-1].ticker is not None and "tiingo" in security.symbols
]
"""The curated securities that trade today, so that their tickers resolve now."""


@cache
def _cached_responses() -> dict[str, list[Path]]:
    """The body of every cached response to Tiingo's daily prices, by symbol."""
    found: dict[str, list[Path]] = defaultdict(list)
    for metadata in sorted(
        (get_settings().data_dir / "raw" / "tiingo").glob("*/*.json")
    ):
        path = urlsplit(json.loads(metadata.read_text(encoding="utf-8"))["url"]).path
        parts = path.split("/")  # "/tiingo/daily/AAPL/prices"
        if parts[1:3] == ["tiingo", "daily"] and parts[-1] == "prices":
            found[parts[3]].append(metadata.with_suffix(".body"))
    return found


def adjusted_closes(symbol: str) -> list[dict[date, float]]:
    """Each cached response for `symbol`, as its adjusted closes by session."""
    return [
        {
            date.fromisoformat(bar["date"][:10]): bar["adjClose"]
            for bar in json.loads(body.read_bytes())
        }
        for body in _cached_responses().get(symbol, [])
    ]


@pytest.fixture(scope="module")
def view() -> Iterator[PointInTimeView]:
    """The local store as the API reads it: pinned to its newest data version, now."""
    store = store_dir(get_settings().data_dir)
    version = latest_data_version(store)
    if version is None:
        pytest.skip("no local store: run `uv run python -m app.data.ingest tiingo`")
    with PointInTimeView(datetime.now(UTC), data_version=version, store=store) as view:
        yield view


@pytest.mark.parametrize("security", LISTED, ids=lambda s: s.symbols["tiingo"])
def test_returns_match_tiingos_adjusted_closes(
    view: PointInTimeView, security: CuratedSecurity
) -> None:
    symbol, ticker = security.symbols["tiingo"], security.history[-1].ticker
    assert ticker is not None
    responses = adjusted_closes(symbol)
    if not responses:
        pytest.skip(f"no cached Tiingo prices for {symbol}")

    def tiingos(start: date, end: date) -> float | None:
        """Tiingo's adjusted return from one session's close to another's, if one
        response has both."""
        for closes in responses:
            if start in closes and end in closes:
                return closes[end] / closes[start] - 1
        return None

    daily = total_returns_as_of(view, ticker)
    days = [
        (day.session_date, day.value, tiingos(day.previous_session, day.session_date))
        for day in daily
    ]
    months = [
        (month.month, month.value, tiingos(month.start_session, month.end_session))
        for month in monthly_total_returns(daily)
        if month.complete
    ]

    for kind, compared in (("day", days), ("month", months)):
        pairs = [
            (when, ours, theirs)
            for when, ours, theirs in compared
            if theirs is not None
        ]
        # Only a session pair split across two responses can't be compared.
        assert len(compared) - len(pairs) < len(responses)
        when, ours, theirs = max(pairs, key=lambda pair: abs(pair[1] - pair[2]))
        assert abs(ours - theirs) <= TOLERANCE, (
            f"{symbol}'s {kind} {when}: {ours} here, {theirs} from Tiingo"
        )
