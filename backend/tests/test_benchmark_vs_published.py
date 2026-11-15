"""SPY's calendar-year total returns against published ones, from the local data (S7.8).

A run's excess return, beta, alpha, and t-statistic are all measured against the
benchmark, so its returns are worth checking against a source outside the project.
The store's bars come from Tiingo, whose terms don't allow committing them (D2), so
this test reads the local store, which CI doesn't have. It's marked `local_data` and
skipped by default: run it with `uv run pytest -m local_data` after `ingest tiingo`.

The published figures are SPY's column of "Annual Total Return (%) History" on Yahoo
Finance (https://finance.yahoo.com/quote/SPY/performance/), read on 2026-11-15. They
are facts about the fund, not Tiingo's data.
"""

from datetime import UTC, date, datetime

import pytest

from app.backtest.returns import DailyReturn, total_returns_as_of
from app.config import get_settings
from app.data import calendar
from app.data.store import store_dir
from app.data.versions import latest_data_version
from app.data.view import PointInTimeView

pytestmark = pytest.mark.local_data

PUBLISHED = {
    2010: 15.06,
    2011: 1.89,
    2012: 15.99,
    2013: 32.31,
    2014: 13.46,
    2015: 1.25,
    2016: 12.00,
    2017: 21.70,
    2018: -4.56,
    2019: 31.22,
    2020: 18.37,
    2021: 28.75,
    2022: -18.17,
    2023: 26.19,
    2024: 24.89,
    2025: 17.72,
}
"""SPY's total return for each calendar year of the canonical spec's period, in
percent."""

TOLERANCE = 0.01
"""In percentage points. The published figures have two decimals, so rounding alone
allows 0.005, which is as far as any year was on data version 20261111T030742Z."""


@pytest.fixture(scope="module")
def daily() -> list[DailyReturn]:
    """SPY's daily total returns from the last close of 2009, from the local store as
    the API reads it: pinned to its newest data version, now."""
    store = store_dir(get_settings().data_dir)
    version = latest_data_version(store)
    if version is None:
        pytest.skip("no local store: run `uv run python -m app.data.ingest tiingo`")
    start = calendar.previous_session(date(min(PUBLISHED), 1, 1))
    with PointInTimeView(datetime.now(UTC), data_version=version, store=store) as view:
        return total_returns_as_of(view, "SPY", start)


@pytest.mark.parametrize("year", PUBLISHED)
def test_spys_year_matches_the_published_return(
    daily: list[DailyReturn], year: int
) -> None:
    days = [day for day in daily if day.session_date.year == year]
    assert days, f"the store has no SPY bars in {year}"
    # The year runs from the last close of the year before to its own last close.
    assert days[0].previous_session == calendar.previous_session(date(year, 1, 1))
    assert days[-1].session_date == calendar.previous_session(date(year + 1, 1, 1))

    growth = 1.0
    for day in days:
        growth *= 1 + day.value
    ours = (growth - 1) * 100

    assert abs(ours - PUBLISHED[year]) <= TOLERANCE, (
        f"SPY returned {ours:.4f}% in {year} here, and {PUBLISHED[year]}% as published"
    )
