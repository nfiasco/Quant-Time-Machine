"""Momentum (S7.4) on a made-up market: a total return over whole months, leaving out
the latest ones (app/backtest/signals/momentum.py; doc/reference/signals.md, section 1).
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.backtest.signals import SignalValue
from app.backtest.signals.momentum import momentum, momentum_window
from app.backtest.spec import MomentumSignal
from app.data.timeutil import market_time
from app.data.view import PointInTimeView
from tests.toy_market import (
    UNIVERSE,
    add_action,
    add_bars,
    add_member,
    add_security,
    steps,
)

DECISION = market_time(date(2021, 1, 4), time(9, 30))
"""January 2021's decision. Its 12-1 momentum runs from the close on 2019-12-31 to the
close on 2020-11-30."""

ALPHA = {
    date(2019, 12, 2): 100.0,
    date(2020, 3, 2): 110.0,  # up 10%
    date(2020, 6, 15): 55.0,  # a 2-for-1 split: no change
    date(2020, 11, 2): 60.5,  # up 10%
    date(2020, 12, 1): 200.0,  # December, which 12-1 momentum leaves out
}
"""Alpha's closes, each from its date until the next one's."""

ALPHA_12_1 = 1.1 * 1.01 * 1.1 - 1
"""Alpha's 12-1 momentum in January 2021: the two 10% rises and a 1% dividend, 0.2221."""


@pytest.fixture
def store(store_dir: Path) -> Path:
    add_security(store_dir, "alpha", "AAA")
    add_member(store_dir, "alpha")
    add_bars(store_dir, "alpha", steps(date(2019, 12, 2), date(2021, 1, 29), ALPHA))
    add_action(store_dir, "alpha", date(2020, 6, 15), "split", 2.0)
    add_action(store_dir, "alpha", date(2020, 9, 15), "dividend", 0.55)
    return store_dir


def add_toy(store: Path, security_id: str, prices: Mapping[date, float]) -> None:
    """Another member with its own closes."""
    add_security(store, security_id, security_id[:3].upper())
    add_member(store, security_id)
    add_bars(store, security_id, prices)


def evaluate(
    store: Path, at: datetime = DECISION, **params: Any
) -> Mapping[str, SignalValue]:
    """Each member's momentum through a view bound to `at`: 12-1 unless `params` say
    otherwise."""
    with PointInTimeView(at, store=store) as view:
        members = view.universe_as_of(UNIVERSE)
        return momentum(view, members, MomentumSignal(type="momentum", **params))


@pytest.mark.parametrize(
    ("day", "lookback", "skip", "window"),
    [
        (date(2020, 6, 1), 12, 1, (date(2019, 5, 31), date(2020, 4, 30))),
        (date(2021, 1, 4), 12, 1, (date(2019, 12, 31), date(2020, 11, 30))),
        (date(2021, 1, 4), 12, 0, (date(2019, 12, 31), date(2020, 12, 31))),
        # February 29, 2020 was a Saturday.
        (date(2020, 4, 1), 3, 1, (date(2019, 12, 31), date(2020, 2, 28))),
        # November 29, 2019, the day after Thanksgiving, closed early.
        (date(2020, 1, 2), 12, 1, (date(2018, 12, 31), date(2019, 11, 29))),
        # Markets reopened on October 31, 2012, after Hurricane Sandy.
        (date(2012, 11, 1), 1, 0, (date(2012, 9, 28), date(2012, 10, 31))),
        # Good Friday, March 29, 2024.
        (date(2024, 5, 1), 1, 0, (date(2024, 3, 28), date(2024, 4, 30))),
    ],
)
def test_the_window_is_whole_months_before_the_decision(
    day: date, lookback: int, skip: int, window: tuple[date, date]
) -> None:
    assert momentum_window(day, lookback, skip) == window


def test_12_1_momentum_compounds_total_returns(store: Path) -> None:
    # The default, from 2019-12-31's close to 2020-11-30's: the split and the dividend
    # count, and December's jump doesn't.
    assert evaluate(store)["alpha"].value == pytest.approx(ALPHA_12_1)


def test_a_later_decision_in_the_month_has_the_same_window(store: Path) -> None:
    # Every January bar is known at the month's last close, but momentum counts whole
    # months only.
    late = market_time(date(2021, 1, 29), time(16))

    assert evaluate(store, late)["alpha"].value == pytest.approx(ALPHA_12_1)


def test_skipping_no_months_includes_the_last_one(store: Path) -> None:
    # December 2020 took alpha from 60.5 to 200.
    value = evaluate(store, skip_months=0)["alpha"].value

    assert value == pytest.approx((1 + ALPHA_12_1) * 200 / 60.5 - 1)


def test_no_value_without_a_close_where_the_window_starts(store: Path) -> None:
    add_toy(
        store,
        "beta",
        steps(date(2020, 2, 3), date(2021, 1, 29), {date(2020, 2, 3): 50.0}),
    )

    found = evaluate(store)

    assert set(found) == {"alpha", "beta"}
    assert found["beta"] == SignalValue(
        None, "It had no close on 2019-12-31, the start of its 12-1 momentum window."
    )


def test_no_value_without_a_close_where_the_window_ends(store: Path) -> None:
    prices = steps(date(2019, 12, 2), date(2021, 1, 29), {date(2019, 12, 2): 50.0})
    del prices[date(2020, 11, 30)]
    add_toy(store, "gamma", prices)

    assert evaluate(store)["gamma"] == SignalValue(
        None, "It had no close on 2020-11-30, the end of its 12-1 momentum window."
    )


def test_no_value_when_an_action_has_no_close(store: Path) -> None:
    prices = steps(date(2019, 12, 2), date(2021, 1, 29), {date(2019, 12, 2): 50.0})
    del prices[date(2020, 8, 14)]
    add_toy(store, "delta", prices)
    add_action(store, "delta", date(2020, 8, 14), "dividend", 1.0)

    assert evaluate(store)["delta"] == SignalValue(
        None,
        "Its total return from 2019-12-31 to 2020-11-30 couldn't be computed: delta "
        "has a corporate action on 2020-08-14 but no close that day.",
    )


def test_momentum_reads_only_its_window(store: Path) -> None:
    with PointInTimeView(DECISION, store=store) as view:
        members = view.universe_as_of(UNIVERSE)
        before = len(view.access_log)
        momentum(view, members, MomentumSignal(type="momentum"))
        read = view.access_log[before:]

    days = {r.key[1] for r in read if r.table in ("price_bars", "corporate_actions")}
    assert {r.table for r in read} == {"securities", "price_bars", "corporate_actions"}
    # Nothing from before the window, or from December, the month it leaves out.
    assert (min(days), max(days)) == (date(2019, 12, 31), date(2020, 11, 30))


@pytest.mark.parametrize(
    "known_at",
    [DECISION + timedelta(microseconds=1), datetime(2099, 1, 1, tzinfo=UTC)],
    ids=["a microsecond after the decision", "in 2099"],
)
def test_a_future_bar_never_reaches_momentum(store: Path, known_at: datetime) -> None:
    # Later versions of a bar and of the split inside the window, as if the vendor had
    # corrected them after the decision.
    add_bars(store, "alpha", {date(2020, 11, 30): 1_000_000.0}, known_at=known_at)
    add_action(store, "alpha", date(2020, 6, 15), "split", 10.0, known_at=known_at)

    assert evaluate(store)["alpha"].value == pytest.approx(ALPHA_12_1)


def test_the_same_rows_count_once_they_are_known(store: Path) -> None:
    # Without this, the test above would pass for a signal that ignored the rows.
    soon = DECISION + timedelta(microseconds=1)
    add_bars(store, "alpha", {date(2020, 11, 30): 1_000_000.0}, known_at=soon)

    value = evaluate(store, soon)["alpha"].value

    assert value == pytest.approx((1 + ALPHA_12_1) * 1_000_000 / 60.5 - 1)
