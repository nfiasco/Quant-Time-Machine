"""The signal library's registry (S7.4): the engine can evaluate every kind of signal a
spec can name (app/backtest/signals/__init__.py)."""

from datetime import date, time
from pathlib import Path

import pytest

from app.backtest.signals import SIGNALS
from app.backtest.spec import (
    MacroChangeSignal,
    MomentumSignal,
    RevenueGrowthAccelerationSignal,
    RevenueGrowthSignal,
    signal_types,
)
from app.data.timeutil import market_time
from app.data.view import PointInTimeView

PARAMS = {
    "momentum": MomentumSignal(type="momentum"),
    "revenue_growth": RevenueGrowthSignal(type="revenue_growth", basis="yoy_quarterly"),
    "revenue_growth_acceleration": RevenueGrowthAccelerationSignal(
        type="revenue_growth_acceleration", basis="yoy_quarterly"
    ),
    "macro_change": MacroChangeSignal(
        type="macro_change", series="UNRATE", releases=1, change="absolute"
    ),
}


def test_the_library_has_every_signal_a_spec_can_name() -> None:
    # In the catalog's order, which doc/reference/signals.md follows.
    assert list(SIGNALS) == [kind.type for kind in signal_types()]


@pytest.mark.parametrize("kind", SIGNALS)
def test_no_members_means_no_reads(fixture_store: Path, kind: str) -> None:
    # A universe has no members before its history starts, as in 2009.
    at = market_time(date(2020, 6, 5), time(9, 30))
    with PointInTimeView(at, store=fixture_store) as view:
        assert SIGNALS[kind](view, [], PARAMS[kind]) == {}
        assert view.access_log == ()
