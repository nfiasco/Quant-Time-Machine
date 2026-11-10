"""Macro change (S7.4): a macro series' change over its latest releases, as published by
the decision (app/backtest/signals/macro.py; doc/reference/signals.md, section 4).

The fixture store holds real ALFRED vintages of the unemployment rate, so the first
tests are time-model.md's June 5, 2020 morning; the others use made-up releases.
"""

from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

import pytest

from app.backtest.signals import SignalValue
from app.backtest.signals.macro import macro_change, period_months
from app.backtest.spec import MacroChangeSignal
from app.data.records import UniverseMember
from app.data.sources.alfred import SERIES
from app.data.timeutil import market_time
from app.data.view import PointInTimeView
from tests.toy_market import UNIVERSE, add_release


def member(security_id: str) -> UniverseMember:
    return UniverseMember(
        universe=UNIVERSE,
        security_id=security_id,
        ticker=security_id[:3].upper(),
        name=f"{security_id} Corp.",
        cik=None,
        added=date(2010, 1, 1),
        available_at=market_time(date(2010, 1, 1), time(0)),
        time_assumed=False,
        source="test",
        source_ref=f"made up: {security_id} joins",
    )


ALPHA, BETA = member("alpha"), member("beta")


def change(
    store: Path,
    at: datetime,
    series: str = "UNRATE",
    releases: int = 1,
    kind: Literal["absolute", "relative"] = "absolute",
) -> SignalValue:
    """The signal's value for a member, through a view bound to `at`."""
    params = MacroChangeSignal(
        type="macro_change", series=series, releases=releases, change=kind
    )
    with PointInTimeView(at, store=store) as view:
        return macro_change(view, [ALPHA], params)[ALPHA.security_id]


def et(day: date, hour: int, minute: int = 0) -> datetime:
    return market_time(day, time(hour, minute))


JUNE_5 = date(2020, 6, 5)


def test_a_change_counts_from_the_jobs_report(fixture_store: Path) -> None:
    # At 09:30 ET, May's first print, 13.3%, came out an hour earlier: down 1.4 points
    # from April's 14.7%. At 08:00, the latest is April's: up 10.3 from March's 4.4%.
    assert change(fixture_store, et(JUNE_5, 9, 30)).value == pytest.approx(-1.4)
    assert change(fixture_store, et(JUNE_5, 8)).value == pytest.approx(10.3)
    # The release counts from 08:30 itself.
    assert change(fixture_store, et(JUNE_5, 8, 30)).value == pytest.approx(-1.4)


def test_each_value_is_its_latest_revision_known_then(fixture_store: Path) -> None:
    # June 2020's 11.1% against April's 14.7%, which a vintage of 2021-01-08 revised
    # to 14.8%.
    before = change(fixture_store, et(date(2020, 12, 1), 9, 30), releases=2)
    after = change(fixture_store, et(date(2021, 2, 1), 9, 30), releases=2)

    assert before.value == pytest.approx(11.1 - 14.7)
    assert after.value == pytest.approx(11.1 - 14.8)


def test_no_value_when_the_latest_observation_is_missing(fixture_store: Path) -> None:
    # October 2025's unemployment rate was never collected, in the government shutdown.
    assert change(fixture_store, et(date(2026, 1, 2), 9, 30)) == SignalValue(
        None, "UNRATE's latest observation, for October 2025, was published as missing."
    )


def test_no_value_before_the_first_vintage(fixture_store: Path) -> None:
    # GDP's first vintage in ALFRED is 1991-12-04; then the observation a quarter
    # before 1985's first is still unknown.
    assert change(fixture_store, et(date(1991, 12, 2), 9, 30), "GDP") == SignalValue(
        None, "No GDP observation had been published by then."
    )
    assert change(fixture_store, et(date(1991, 12, 5), 9, 30), "GDP") == SignalValue(
        None, "GDP's observation for Q4 1984 hadn't been published by then."
    )


def test_a_relative_change_is_a_fraction(store_dir: Path) -> None:
    add_release(store_dir, "CPIAUCSL", date(2020, 1, 1), 100.0, date(2020, 2, 13))
    add_release(store_dir, "CPIAUCSL", date(2021, 1, 1), 103.0, date(2021, 2, 10))
    at = et(date(2021, 3, 1), 9, 30)

    assert change(store_dir, at, "CPIAUCSL", 12, "relative").value == pytest.approx(
        0.03
    )
    assert change(store_dir, at, "CPIAUCSL", 12).value == pytest.approx(3.0)


def test_a_quarterly_series_steps_by_quarters(store_dir: Path) -> None:
    add_release(store_dir, "GDP", date(2020, 1, 1), 21_500.0, date(2020, 4, 29))
    add_release(store_dir, "GDP", date(2020, 4, 1), 19_500.0, date(2020, 7, 30))
    at = et(date(2020, 8, 3), 9, 30)

    assert change(store_dir, at, "GDP").value == pytest.approx(-2_000.0)
    assert change(store_dir, at, "GDP", kind="relative").value == pytest.approx(
        19_500 / 21_500 - 1
    )


def test_a_release_counts_from_its_time_of_day(store_dir: Path) -> None:
    # The Fed's H.15 release comes out at 16:15 ET: on June 1, 2020, a 09:30 decision
    # still sees April's rate as the latest.
    for month, rate, vintage in [(3, 0.65, 4), (4, 0.05, 5), (5, 0.05, 6)]:
        add_release(
            store_dir, "FEDFUNDS", date(2020, month, 1), rate, date(2020, vintage, 1)
        )
    june_1 = date(2020, 6, 1)

    assert change(store_dir, et(june_1, 9, 30), "FEDFUNDS").value == pytest.approx(-0.6)
    assert change(store_dir, et(june_1, 16, 15), "FEDFUNDS").value == pytest.approx(0)


def test_no_value_for_a_relative_change_from_zero(store_dir: Path) -> None:
    add_release(store_dir, "FEDFUNDS", date(2020, 4, 1), 0.0, date(2020, 5, 1))
    add_release(store_dir, "FEDFUNDS", date(2020, 5, 1), 0.05, date(2020, 6, 1))
    at = et(date(2020, 6, 2), 9, 30)

    assert change(store_dir, at, "FEDFUNDS").value == pytest.approx(0.05)
    assert change(store_dir, at, "FEDFUNDS", kind="relative") == SignalValue(
        None,
        "FEDFUNDS was 0 for April 2020, so a relative change from it isn't defined.",
    )


def test_no_value_when_the_earlier_observation_is_missing(store_dir: Path) -> None:
    # BLS published November 2025 on December 16, with October's left out.
    add_release(store_dir, "UNRATE", date(2025, 10, 1), None, date(2025, 12, 16))
    add_release(store_dir, "UNRATE", date(2025, 11, 1), 4.6, date(2025, 12, 16))

    assert change(store_dir, et(date(2026, 1, 2), 9, 30)) == SignalValue(
        None, "UNRATE's observation for October 2025 was published as missing."
    )
    assert change(store_dir, et(date(2026, 1, 2), 9, 30), releases=2) == SignalValue(
        None, "UNRATE's observation for September 2025 hadn't been published by then."
    )


def test_every_member_gets_the_same_value(fixture_store: Path) -> None:
    params = MacroChangeSignal(
        type="macro_change", series="UNRATE", releases=1, change="absolute"
    )
    with PointInTimeView(et(JUNE_5, 9, 30), store=fixture_store) as view:
        found = macro_change(view, [ALPHA, BETA], params)
        read = view.access_log

    assert found["alpha"] == found["beta"]
    assert found["alpha"].value == pytest.approx(-1.4)
    # The latest observation and the one a release before it: two rows.
    assert [(r.table, r.key) for r in read] == [
        ("macro_observations", ("UNRATE", date(2020, 5, 1))),
        ("macro_observations", ("UNRATE", date(2020, 4, 1))),
    ]


def test_every_catalog_series_has_a_supported_frequency() -> None:
    assert {series: period_months(series) for series in SERIES} == {
        "UNRATE": 1,
        "PAYEMS": 1,
        "CPIAUCSL": 1,
        "GDP": 3,
        "FEDFUNDS": 1,
        "TB3MS": 1,
    }


@pytest.fixture
def jobs(store_dir: Path) -> Path:
    """April and May 2020's first prints, as the June 5 morning knew them."""
    add_release(store_dir, "UNRATE", date(2020, 4, 1), 14.7, date(2020, 5, 8))
    add_release(store_dir, "UNRATE", date(2020, 5, 1), 13.3, JUNE_5)
    return store_dir


@pytest.mark.parametrize(
    "vintage",
    [date(2020, 6, 8), date(2099, 1, 1)],
    ids=["the next Monday", "in 2099"],
)
def test_a_future_release_never_reaches_macro_change(jobs: Path, vintage: date) -> None:
    # A revision of April, and June's first print, published after the decision.
    add_release(jobs, "UNRATE", date(2020, 4, 1), 20.0, vintage)
    add_release(jobs, "UNRATE", date(2020, 6, 1), 99.9, max(vintage, date(2020, 7, 2)))

    assert change(jobs, et(JUNE_5, 9, 30)).value == pytest.approx(-1.4)


def test_the_same_release_counts_once_it_is_published(jobs: Path) -> None:
    # Without this, the test above would pass for a signal that ignored the rows.
    add_release(jobs, "UNRATE", date(2020, 4, 1), 20.0, date(2020, 6, 8))

    assert change(jobs, et(date(2020, 6, 8), 8, 30)).value == pytest.approx(13.3 - 20)
