"""Momentum: a security's total return over whole months, leaving out the latest ones
(S7.4; doc/reference/signals.md, section 1).

For a decision in month M, with a lookback of L months and a skip of S, momentum runs
from the close of `start`, the last session before month M − L, to the close of `end`,
the last session before month M − S:

    momentum = Π (1 + r_t) − 1, over the sessions t after `start` through `end`

r_t is the session's total return, k_t × (close_t + div_t) / close_(t−1) − 1
(app/backtest/returns.py), so splits and dividends count and prices stay as traded. 12-1
momentum, the default, compounds the 11 months before the last one: at the June 1, 2020
decision, from the close on May 31, 2019 to the close on April 30, 2020, leaving out May.

Data: the security's daily bars and its splits and dividends from `start` through
`end`, read by its ID through the decision's view. The window ends before the
decision's month begins, so all of it was known then (doc/reference/time-model.md,
rule 4), at any decision time.

Minimum history: a close on `start` and on `end`. A security whose prices start later,
or that has no bar on one of them, has no value, and the reason says which day.
"""

from collections.abc import Sequence
from datetime import date

from app.backtest.returns import daily_total_returns
from app.backtest.signals.base import SignalValue, decision_day, months_before
from app.backtest.spec import MomentumSignal
from app.data import calendar
from app.data.records import UniverseMember
from app.data.view import PointInTimeView


def momentum_window(
    day: date, lookback_months: int, skip_months: int
) -> tuple[date, date]:
    """The sessions whose closes momentum runs between, for a decision on `day`: the
    last session before the month `lookback_months` before `day`'s, and the last one
    before the month `skip_months` before it. For 12-1 momentum at the June 1, 2020
    decision, May 31, 2019 and April 30, 2020."""
    month = day.replace(day=1)
    start = calendar.previous_session(months_before(month, lookback_months))
    end = calendar.previous_session(months_before(month, skip_months))
    return start, end


def momentum(
    view: PointInTimeView, members: Sequence[UniverseMember], params: MomentumSignal
) -> dict[str, SignalValue]:
    """Each member's momentum as known at the view's knowledge time, by security ID."""
    if not members:
        return {}
    start, end = momentum_window(
        decision_day(view), params.lookback_months, params.skip_months
    )
    window = f"{params.lookback_months}-{params.skip_months} momentum window"
    return {
        member.security_id: _momentum(view, member, start, end, window)
        for member in members
    }


def _momentum(
    view: PointInTimeView, member: UniverseMember, start: date, end: date, window: str
) -> SignalValue:
    """One member's total return from the close of `start` to the close of `end`."""
    security = view.get_security(member.security_id)
    bars = view.get_price_series_as_of(security, start, end)
    # A close counts as daily_total_returns counts one: there, and above zero.
    closes = [
        bar.session_date for bar in bars if bar.close is not None and bar.close > 0
    ]
    if not closes or closes[0] != start:
        return SignalValue(
            None, f"It had no close on {start}, the start of its {window}."
        )
    if closes[-1] != end:
        return SignalValue(None, f"It had no close on {end}, the end of its {window}.")
    actions = view.get_corporate_actions_as_of(security, start, end)
    try:
        daily = daily_total_returns(bars, actions)
    except ValueError as error:  # an action on a day without a close
        return SignalValue(
            None,
            f"Its total return from {start} to {end} couldn't be computed: {error}.",
        )
    growth = 1.0
    for day in daily:
        growth *= 1 + day.value
    return SignalValue(growth - 1)
