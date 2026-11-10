"""Revenue growth and its acceleration (S7.4), from made-up quarters filed on made-up
dates (app/backtest/signals/revenue.py; doc/reference/signals.md, sections 2 and 3).
"""

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from app.backtest.signals import SignalValue
from app.backtest.signals.revenue import revenue_growth, revenue_growth_acceleration
from app.backtest.spec import (
    RevenueGrowthAccelerationSignal,
    RevenueGrowthSignal,
)
from app.config import get_settings
from app.data.store import store_dir
from app.data.timeutil import market_time
from app.data.versions import latest_data_version
from app.data.view import PointInTimeView
from tests.toy_market import (
    UNIVERSE,
    add_fact,
    add_member,
    add_revenue,
    add_security,
)

type Kind = Callable[..., Mapping[str, SignalValue]]

CIK = 1001

QUARTERS = {
    date(2019, 9, 30): 80.0,
    date(2019, 12, 31): 90.0,
    date(2020, 3, 31): 100.0,
    date(2020, 6, 30): 100.0,
    date(2020, 9, 30): 100.0,
    date(2020, 12, 31): 99.0,  # 10% more than a year earlier
    date(2021, 3, 31): 120.0,  # 20% more
}
"""Alpha's revenue by quarter, each in a 10-Q accepted at 16:30 ET 40 days after the
quarter's end."""

FILED = market_time(date(2021, 5, 10), time(16, 30))
"""When the 10-Q for the quarter ended 2021-03-31, the last one, was accepted."""

DECISION = market_time(date(2021, 6, 1), time(9, 30))

PARAMS = {
    revenue_growth: RevenueGrowthSignal(type="revenue_growth", basis="yoy_quarterly"),
    revenue_growth_acceleration: RevenueGrowthAccelerationSignal(
        type="revenue_growth_acceleration", basis="yoy_quarterly"
    ),
}


@pytest.fixture
def store(store_dir: Path) -> Path:
    add_security(store_dir, "alpha", "AAA", cik=CIK)
    add_member(store_dir, "alpha")
    add_revenue(store_dir, CIK, QUARTERS)
    return store_dir


def evaluate(
    store: Path, kind: Kind, at: datetime = DECISION
) -> Mapping[str, SignalValue]:
    """`kind` for each member, through a view bound to `at`."""
    with PointInTimeView(at, store=store) as view:
        return kind(view, view.universe_as_of(UNIVERSE), PARAMS[kind])


def value(store: Path, kind: Kind, at: datetime = DECISION) -> float | None:
    return evaluate(store, kind, at)["alpha"].value


def test_growth_is_the_latest_quarter_over_the_same_quarter_a_year_earlier(
    store: Path,
) -> None:
    # The quarter ended 2021-03-31 against the one ended 2020-03-31: 120 / 100 - 1.
    assert value(store, revenue_growth) == pytest.approx(0.20)


def test_acceleration_is_this_quarters_growth_minus_last_quarters(
    store: Path,
) -> None:
    # 20% growth, after 99 / 90 - 1 = 10% the quarter before.
    assert value(store, revenue_growth_acceleration) == pytest.approx(0.10)


def test_a_53_week_year_still_matches_its_quarters(store_dir: Path) -> None:
    # A fiscal calendar like Apple's: its fiscal 2023 began with a 14-week quarter,
    # which ended 371 days after the same quarter a year earlier.
    add_security(store_dir, "alpha", "AAA", cik=CIK)
    add_member(store_dir, "alpha")
    quarters = [
        (date(2021, 6, 27), date(2021, 9, 25), 100.0),
        (date(2021, 9, 26), date(2021, 12, 25), 100.0),
        (date(2022, 6, 26), date(2022, 9, 24), 110.0),
        (date(2022, 9, 25), date(2022, 12, 31), 120.0),  # 98 days
    ]
    for start, end, revenue in quarters:
        accepted = market_time(end + timedelta(days=35), time(18))
        add_fact(store_dir, CIK, start, end, revenue, accepted=accepted)
    at = market_time(date(2023, 3, 1), time(9, 30))

    assert value(store_dir, revenue_growth, at) == pytest.approx(0.20)
    assert value(store_dir, revenue_growth_acceleration, at) == pytest.approx(0.10)


def test_a_fourth_quarter_derived_from_the_year_counts(store_dir: Path) -> None:
    # No filing reports the fourth quarter of 2020: it's the 10-K's year, 410, minus
    # the nine months the third quarter's 10-Q reported, 300, known from the 10-K.
    add_security(store_dir, "alpha", "AAA", cik=CIK)
    add_member(store_dir, "alpha")
    add_revenue(store_dir, CIK, {date(2019, 12, 31): 100.0})
    q3 = market_time(date(2020, 11, 5), time(16, 30))
    add_fact(store_dir, CIK, date(2020, 1, 1), date(2020, 9, 30), 300.0, accepted=q3)
    annual = market_time(date(2021, 2, 20), time(16, 30))
    add_fact(
        store_dir,
        CIK,
        date(2020, 1, 1),
        date(2020, 12, 31),
        410.0,
        accepted=annual,
        form="10-K",
    )

    at = market_time(date(2021, 3, 1), time(9, 30))
    assert value(store_dir, revenue_growth, at) == pytest.approx(0.10)
    # Before the 10-K, the latest quarter known is a year older.
    assert evaluate(store_dir, revenue_growth, annual - timedelta(seconds=1)) == {
        "alpha": SignalValue(
            None,
            "Its latest quarter known ended on 2019-12-31, 417 days before: more than "
            "200, so later quarters are missing.",
        )
    }


def test_a_16_week_quarter_isnt_a_quarter(store_dir: Path) -> None:
    # PepsiCo's year is three 12-week quarters and a 16-week fourth, 112 days, longer
    # than any quarter reads recognize (app/data/fundamentals.py). Its first quarter has
    # growth, but no quarter before it.
    add_security(store_dir, "pepsi", "PPP", cik=CIK)
    add_member(store_dir, "pepsi")
    quarters = [
        (date(2018, 12, 30), date(2019, 3, 23), 100.0),
        (date(2019, 9, 8), date(2019, 12, 28), 150.0),
        (date(2019, 12, 29), date(2020, 3, 21), 105.0),
    ]
    for start, end, revenue in quarters:
        accepted = market_time(end + timedelta(days=40), time(16))
        add_fact(store_dir, CIK, start, end, revenue, accepted=accepted)
    at = market_time(date(2020, 5, 1), time(9, 30))

    assert evaluate(store_dir, revenue_growth, at)["pepsi"].value == pytest.approx(0.05)
    assert evaluate(store_dir, revenue_growth_acceleration, at) == {
        "pepsi": SignalValue(
            None,
            "Revenue for the quarter before the one that ended on 2020-03-21 wasn't "
            "known.",
        )
    }


def test_a_restatement_counts_from_its_own_filing(store: Path) -> None:
    # A 10-Q/A restates the quarter ended 2020-03-31 from 100 to 96.
    amended = market_time(date(2021, 5, 20), time(17))
    add_fact(
        store,
        CIK,
        date(2020, 1, 1),
        date(2020, 3, 31),
        96.0,
        accepted=amended,
        form="10-Q/A",
    )

    assert value(store, revenue_growth, amended - timedelta(seconds=1)) == (
        pytest.approx(0.20)
    )
    assert value(store, revenue_growth, amended) == pytest.approx(120 / 96 - 1)


@pytest.mark.parametrize("kind", PARAMS)
def test_no_value_before_any_revenue_was_filed(store_dir: Path, kind: Kind) -> None:
    # A fund such as SPY has no CIK, and a company may not have filed yet.
    add_security(store_dir, "fund", "FFF")
    add_security(store_dir, "alpha", "AAA", cik=CIK)
    for security_id in ("fund", "alpha"):
        add_member(store_dir, security_id)

    assert evaluate(store_dir, kind) == {
        "fund": SignalValue(None, "No quarterly revenue was known then."),
        "alpha": SignalValue(None, "No quarterly revenue was known then."),
    }


@pytest.mark.parametrize("kind", PARAMS)
def test_no_value_when_the_latest_quarter_is_old(store: Path, kind: Kind) -> None:
    # The quarter ended 2021-03-31 is 200 days old on 2021-10-17, and too old a day
    # later: a company that files on time would have reported the next one.
    on_the_line = market_time(date(2021, 10, 17), time(9, 30))
    too_old = market_time(date(2021, 10, 18), time(9, 30))

    assert value(store, kind, on_the_line) is not None
    assert evaluate(store, kind, too_old)["alpha"] == SignalValue(
        None,
        "Its latest quarter known ended on 2021-03-31, 201 days before: more than "
        "200, so later quarters are missing.",
    )


def test_growth_needs_the_quarter_a_year_earlier(store_dir: Path) -> None:
    add_security(store_dir, "alpha", "AAA", cik=CIK)
    add_member(store_dir, "alpha")
    add_revenue(store_dir, CIK, {date(2020, 12, 31): 99.0, date(2021, 3, 31): 120.0})

    assert evaluate(store_dir, revenue_growth)["alpha"] == SignalValue(
        None,
        "Revenue for the quarter a year before the one that ended on 2021-03-31 "
        "wasn't known.",
    )


def test_acceleration_needs_the_quarter_before(store_dir: Path) -> None:
    add_security(store_dir, "alpha", "AAA", cik=CIK)
    add_member(store_dir, "alpha")
    add_revenue(store_dir, CIK, {date(2020, 3, 31): 100.0, date(2021, 3, 31): 120.0})

    assert value(store_dir, revenue_growth) == pytest.approx(0.20)
    assert evaluate(store_dir, revenue_growth_acceleration)["alpha"] == SignalValue(
        None,
        "Revenue for the quarter before the one that ended on 2021-03-31 wasn't known.",
    )


@pytest.mark.parametrize("kind", PARAMS)
def test_growth_needs_positive_revenue(store: Path, kind: Kind) -> None:
    # A 10-Q/A restates the quarter ended 2020-03-31 to nothing.
    add_fact(
        store,
        CIK,
        date(2020, 1, 1),
        date(2020, 3, 31),
        0.0,
        accepted=FILED,
        form="10-Q/A",
    )

    assert evaluate(store, kind)["alpha"] == SignalValue(
        None,
        "Revenue for the quarter that ended on 2020-03-31 wasn't positive, so growth "
        "isn't defined.",
    )


@pytest.mark.parametrize(
    ("kind", "then", "after"),
    [
        # Then the latest quarter is the one ended 2020-12-31: 10% growth, after 25%
        # (100 / 80 - 1) the quarter before. After, it's the one ended 2021-03-31.
        (revenue_growth, 0.10, 0.20),
        (revenue_growth_acceleration, 0.10 - 0.25, 0.20 - 0.10),
    ],
    ids=["growth", "acceleration"],
)
def test_a_future_filing_never_reaches_revenue_signals(
    store: Path, kind: Kind, then: float, after: float
) -> None:
    # A restatement of the quarter ended 2020-12-31, accepted only in 2099.
    add_fact(
        store,
        CIK,
        date(2020, 10, 1),
        date(2020, 12, 31),
        1_000_000.0,
        accepted=datetime(2099, 1, 1, tzinfo=UTC),
        form="10-K/A",
    )

    # A second before the last 10-Q was accepted, its quarter is unknown.
    assert value(store, kind, FILED - timedelta(seconds=1)) == pytest.approx(then)
    # From its acceptance on, it counts, but the restatement still doesn't.
    assert value(store, kind, FILED) == pytest.approx(after)


def test_every_member_gets_a_value_or_a_reason(store: Path) -> None:
    add_security(store, "beta", "BBB")
    add_member(store, "beta")

    with PointInTimeView(DECISION, store=store) as view:
        members = view.universe_as_of(UNIVERSE)
        for kind, params in PARAMS.items():
            assert set(kind(view, members, params)) == {"alpha", "beta"}


@pytest.mark.local_data
def test_apples_revenue_signals_on_june_1_2020() -> None:
    # SEC's numbers are public, so this checks the local store against Apple's 10-Qs:
    # $58,313 million for its fiscal second quarter of 2020 against $58,015 million a
    # year earlier, and $91,819 million for its first quarter against $84,310 million.
    store = store_dir(get_settings().data_dir)
    version = latest_data_version(store)
    if version is None:
        pytest.skip("no local store: run `uv run python -m app.data.ingest sec`")
    at = market_time(date(2020, 6, 1), time(9, 30))
    with PointInTimeView(at, data_version=version, store=store) as view:
        apple = [m for m in view.universe_as_of(UNIVERSE) if m.ticker == "AAPL"]
        growth = revenue_growth(view, apple, PARAMS[revenue_growth])["apple"]
        acceleration = revenue_growth_acceleration(
            view, apple, PARAMS[revenue_growth_acceleration]
        )["apple"]

    assert growth.value == pytest.approx(58_313 / 58_015 - 1)  # 0.51%
    assert acceleration.value == pytest.approx(
        (58_313 / 58_015 - 1) - (91_819 / 84_310 - 1)  # -8.39 points
    )
