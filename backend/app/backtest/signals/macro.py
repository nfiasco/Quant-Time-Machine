"""Macro change: a macro series' change over its latest releases, as published by the
decision (S7.4; doc/reference/signals.md, section 4).

For a series x and k releases:

    absolute  x(t) − x(t − k)
    relative  x(t) / x(t − k) − 1

x(t) is the latest observation published by the decision, and x(t − k) the observation
k periods before it: k months for a monthly series, k quarters for a quarterly one. Each
is at its latest version published by then (doc/reference/time-model.md, rule 7), so a
revision counts from its own release. A release, here, is a new observation: a vintage
that only revises earlier observations changes their values but not t.

An absolute change is in the series' units, such as percentage points for UNRATE, and a
relative one is a fraction: 0.03 is 3%. Every security gets the same value, so a filter
on it holds securities only while a condition holds: "unrate_3m < 0" holds them while
unemployment is lower than three months before. At 09:30 ET on June 5, 2020, UNRATE's
absolute change over 1 release is May's first print minus April's, 13.3 − 14.7 = −1.4
points. At 08:00, before the jobs report, it's April's minus March's, 14.7 − 4.4 = 10.3.

Data: two observations, each read at its latest version known at the decision.

Minimum history: x(t) and x(t − k), each published with a value. Before a series' first
vintage in ALFRED, such as FEDFUNDS's on 1996-12-03, nothing was published, so there's
no value, with the reason.
"""

from collections.abc import Mapping, Sequence
from datetime import date

from app.backtest.signals.base import SignalValue, months_before
from app.backtest.spec import MacroChangeSignal
from app.data.records import UniverseMember
from app.data.sources.alfred import SERIES
from app.data.view import PointInTimeView

PERIOD_MONTHS: Mapping[str, int] = {"Monthly": 1, "Quarterly": 3}
"""How many months apart a series' observations are, by its frequency in the macro
catalog (app/data/sources/alfred_series.toml)."""


def macro_change(
    view: PointInTimeView, members: Sequence[UniverseMember], params: MacroChangeSignal
) -> dict[str, SignalValue]:
    """The series' change as published by the view's knowledge time: the same value, or
    the same reason, for every member, by security ID. Without members, it reads
    nothing."""
    if not members:
        return {}
    found = _change(view, params)
    return {member.security_id: found for member in members}


def period_months(series: str) -> int:
    """How many months apart a catalog series' observations are. Raises ValueError for
    a frequency other than monthly or quarterly."""
    frequency = SERIES[series].frequency
    if frequency not in PERIOD_MONTHS:
        raise ValueError(
            f"{series} is {frequency.lower()}, but a macro change needs a monthly or "
            "quarterly series"
        )
    return PERIOD_MONTHS[frequency]


def _change(view: PointInTimeView, params: MacroChangeSignal) -> SignalValue:
    series, months = params.series, period_months(params.series)
    latest = view.get_macro_as_of(series)
    if latest is None:
        return SignalValue(None, f"No {series} observation had been published by then.")
    if latest.value is None:
        return SignalValue(
            None,
            f"{series}'s latest observation, for {_label(latest.period, months)}, was "
            "published as missing.",
        )
    period = months_before(latest.period, months * params.releases)
    earlier = view.get_macro_as_of(series, period)
    if earlier is None:
        return SignalValue(
            None,
            f"{series}'s observation for {_label(period, months)} hadn't been "
            "published by then.",
        )
    if earlier.value is None:
        return SignalValue(
            None,
            f"{series}'s observation for {_label(period, months)} was published as "
            "missing.",
        )
    if params.change == "absolute":
        return SignalValue(latest.value - earlier.value)
    if earlier.value <= 0:
        return SignalValue(
            None,
            f"{series} was {earlier.value:g} for {_label(period, months)}, so a "
            "relative change from it isn't defined.",
        )
    return SignalValue(latest.value / earlier.value - 1)


def _label(period: date, months: int) -> str:
    """An observation's period as people write it: "May 2020", or "Q1 2020"."""
    if months == 3:
        return f"Q{(period.month - 1) // 3 + 1} {period.year}"
    return f"{period:%B %Y}"
