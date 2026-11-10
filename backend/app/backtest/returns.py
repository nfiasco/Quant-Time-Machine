"""Total returns from raw prices, splits, and dividends (S6.4; doc/reference/time-model.md, rule 4).

Prices stay as traded everywhere else, so a signal that needs a price level, such as
market cap (S6.6), uses a raw close. Splits and dividends enter only here. A session's
total return is

    r_t = k_t * (close_t + div_t) / close_{t-1} - 1

- `close_t` is the session's raw close, and `close_{t-1}` the previous bar's.
- `k_t` is the split factor with ex-date t (new shares per old share), rounded by
  `round_split_factor`, or 1.
- `div_t` is the cash dividend per share with ex-date t, or 0. Adding it to the close
  reinvests it at that day's close.

A day's return is known at its session's close, with its bar, and a month's return
compounds its sessions'. Adjusted prices are never used: a vendor rescales them after
every later split and dividend, so they carry the future. These returns reproduce
Tiingo's adjusted closes anyway (tests/test_returns_vs_tiingo.py).
"""

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from fractions import Fraction

from app.data import calendar
from app.data.records import CorporateAction, PriceBar
from app.data.view import PointInTimeView

SIMPLE_RATIO_SIDE = 10
"""The largest smaller side of a ratio a split factor rounds to, as in 3-for-2,
4-for-3, or 1-for-10."""

SPLIT_FACTOR_TOLERANCE = 1e-5
"""How close a vendor's split factor must be to a simple ratio to round to it, relative
to the ratio. Tiingo's 7.000007 for Apple's 7-for-1 in 2014 is 1e-6 away."""


@dataclass(frozen=True)
class DailyReturn:
    """A session's total return, from the previous bar's close to this one's."""

    security_id: str
    session_date: date
    previous_session: date
    """The session of the close it starts from: the session before, unless bars are
    missing in between."""
    value: float
    """0.01 is 1%."""
    split_factor: float
    """The split factor with this ex-date, rounded, or 1."""
    dividend: float
    """The cash dividend per share with this ex-date, or 0."""
    available_at: datetime
    """The session's close, when its bar became known."""


@dataclass(frozen=True)
class MonthlyReturn:
    """A calendar month's total return, compounded from its sessions' daily returns."""

    security_id: str
    month: date
    """The month's first day: 2020-08-01 is August 2020."""
    start_session: date
    """The session of the close it starts from."""
    end_session: date
    """The last session compounded."""
    value: float
    complete: bool
    """Whether it runs from the previous month's last session to this month's last.
    A security's first month, or a month not over yet, isn't complete."""
    available_at: datetime
    """The last session's close."""


def round_split_factor(factor: float) -> float:
    """A vendor's split factor, rounded to the simple ratio it stands for.

    Tiingo's factors carry noise: Apple's 7-for-1 in 2014 comes as 7.000007, and
    NVIDIA's 3-for-2 in 2007 as 1.49999925. A factor within 0.001% of a ratio whose
    smaller side is at most 10, such as 7, 3/2, 4/3, or 1/10, becomes that ratio. Any
    other factor is kept as given. Tiingo folds a spin-off into the split factor, such
    as IBM's 1.046 for Kyndryl on 2021-11-04, so the spun-off shares count as
    reinvested in the parent.
    """
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError(f"a split factor must be a positive number, not {factor}")
    if factor >= 1:
        ratio = Fraction(factor).limit_denominator(SIMPLE_RATIO_SIDE)
    else:
        ratio = 1 / Fraction(1 / factor).limit_denominator(SIMPLE_RATIO_SIDE)
    if abs(float(ratio) / factor - 1) <= SPLIT_FACTOR_TOLERANCE:
        return float(ratio)
    return factor


def daily_total_returns(
    bars: Sequence[PriceBar], actions: Sequence[CorporateAction]
) -> list[DailyReturn]:
    """Each session's total return from one security's bars and actions, oldest first.

    `bars` come oldest first, as `get_price_series_as_of` returns them, and `actions`
    are the same security's splits and dividends. The first bar with a close starts the
    series and has no return of its own, so actions up to its date are ignored. A bar
    without a close counts as missing: the next return starts from the last close
    before it, and its `previous_session` shows the gap.

    Raises ValueError for bars out of order or of more than one security, and for an
    action on a later day without a close, because each action comes with its ex-date's
    bar (S6.2).
    """
    _check_series("bars", bars)
    splits: dict[date, float] = {}
    dividends: dict[date, float] = {}
    for action in actions:
        if bars and action.security_id != bars[0].security_id:
            raise ValueError(
                f"an action of {action.security_id} among {bars[0].security_id}'s bars"
            )
        by_date = {"split": splits, "dividend": dividends}.get(action.action)
        if by_date is None:
            raise ValueError(f"unknown corporate action {action.action!r}")
        if action.ex_date in by_date:
            raise ValueError(f"two {action.action}s on {action.ex_date}")
        by_date[action.ex_date] = action.value

    priced = [
        (bar, bar.close) for bar in bars if bar.close is not None and bar.close > 0
    ]
    sessions = {bar.session_date for bar, _ in priced}
    unpriced = sorted(
        day
        for day in splits.keys() | dividends.keys()
        if priced and day > priced[0][0].session_date and day not in sessions
    )
    if unpriced:
        raise ValueError(
            f"{bars[0].security_id} has a corporate action on {unpriced[0]} but no "
            "close that day"
        )

    returns = []
    for (previous, previous_close), (bar, close) in itertools.pairwise(priced):
        split = round_split_factor(splits.get(bar.session_date, 1.0))
        dividend = dividends.get(bar.session_date, 0.0)
        returns.append(
            DailyReturn(
                security_id=bar.security_id,
                session_date=bar.session_date,
                previous_session=previous.session_date,
                value=split * (close + dividend) / previous_close - 1,
                split_factor=split,
                dividend=dividend,
                available_at=bar.available_at,
            )
        )
    return returns


def monthly_total_returns(daily: Sequence[DailyReturn]) -> list[MonthlyReturn]:
    """Each calendar month's total return, compounded from its daily returns, oldest
    first.

    A month's return runs from the close its first daily return starts from to its last
    session's close. Raises ValueError for daily returns out of order or of more than
    one security.
    """
    _check_series("daily returns", daily)
    months = []
    for month, group in itertools.groupby(
        daily, key=lambda day: day.session_date.replace(day=1)
    ):
        days = list(group)
        growth = 1.0
        for day in days:
            growth *= 1 + day.value
        start, end = days[0].previous_session, days[-1].session_date
        months.append(
            MonthlyReturn(
                security_id=days[0].security_id,
                month=month,
                start_session=start,
                end_session=end,
                value=growth - 1,
                complete=(
                    start == calendar.previous_session(month)
                    and end == calendar.previous_session(_next_month(month))
                ),
                available_at=days[-1].available_at,
            )
        )
    return months


def total_returns_as_of(
    view: PointInTimeView,
    ticker: str,
    start: date | None = None,
    end: date | None = None,
) -> list[DailyReturn]:
    """A security's daily total returns as known at the view's knowledge time, oldest
    first.

    They run from the close of the first bar on or after `start` to the last bar on or
    before `end` (both optional), so a holding period that starts at a session's close
    starts at that session. At 09:30 ET on September 1, 2020, Apple's returns from
    2020-07-31 cover August's sessions and include the 4-for-1 split of August 31. The
    bars and actions are read through `view`, so only what was known by then counts,
    and every row read is in its access log. The ticker is resolved at the knowledge
    time, as for `get_price_as_of`.
    """
    bars = view.get_price_series_as_of(ticker, start, end)
    actions = view.get_corporate_actions_as_of(ticker, start, end)
    return daily_total_returns(bars, actions)


def _check_series(kind: str, items: Sequence[PriceBar] | Sequence[DailyReturn]) -> None:
    """Raise ValueError unless `items` are one security's, in session order."""
    for previous, item in itertools.pairwise(items):
        if item.security_id != previous.security_id:
            raise ValueError(
                f"{kind} of {previous.security_id} and {item.security_id} are mixed"
            )
        if item.session_date <= previous.session_date:
            raise ValueError(
                f"{kind} must be in session order, but {item.session_date} follows "
                f"{previous.session_date}"
            )


def _next_month(month: date) -> date:
    """The first day of the month after `month`'s."""
    return date(month.year + month.month // 12, month.month % 12 + 1, 1)
