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

A holding's return runs from the price it was bought at to the price it's valued at,
each a session's open or close (S7.3): `holding_return`. Between them it compounds the
daily returns above. Only a session in which the security traded has a price a trade
could get or a holding could be valued at. Tiingo also has bars for sessions that
didn't trade: one with no volume that repeats the previous close, such as Twitter's on
October 28, 2022, and leftovers after a delisting, such as 353 shares of Xilinx on
February 14, 2022, though Nasdaq had halted it before that day's open.
"""

import itertools
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from fractions import Fraction
from typing import Literal

from app.data import calendar
from app.data.records import CorporateAction, PriceBar, Security
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


@dataclass(frozen=True)
class PricePoint:
    """A price a trade gets or a holding is valued at: one session's open or close."""

    session: date
    price: Literal["open", "close"]

    @property
    def time(self) -> datetime:
        """When the price was set, in UTC: the session's open or its close."""
        if self.price == "open":
            return calendar.session_open(self.session)
        return calendar.session_close(self.session)

    def __str__(self) -> str:
        return f"{self.session.isoformat()} {self.price}"


@dataclass(frozen=True)
class HoldingReturn:
    """A holding's total return from the price it was bought at to the price it was
    valued at (S7.3)."""

    security_id: str
    entry: PricePoint
    exit: PricePoint
    """Where it was valued: the exit asked for, or, if its bars ended before it, its
    last close."""
    value: float
    """0.01 is 1%."""
    complete: bool
    """Whether it reached the exit asked for. Not when the security stopped trading
    first, or its bar for the exit is missing."""


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
    splits, dividends = _by_ex_date(actions, bars[0].security_id if bars else None)

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


def fills_at(bars: Sequence[PriceBar], point: PricePoint) -> bool:
    """Whether a trade could fill at `point`, among one security's bars: its session
    has a bar with that price and a close, both above zero, and some volume. A holding
    bought at an open needs that day's close too, to be valued from it on.

    A bar with zero volume is a session in which nothing traded: Tiingo repeats the
    previous close in it. A bar without a volume counts as traded.
    """
    bar = next((bar for bar in bars if bar.session_date == point.session), None)
    if bar is None or not _traded(bar):
        return False
    price = bar.open if point.price == "open" else bar.close
    return _positive(price) and _positive(bar.close)


def holding_return(
    bars: Sequence[PriceBar],
    actions: Sequence[CorporateAction],
    entry: PricePoint,
    exit: PricePoint,
) -> HoldingReturn | None:
    """A holding's total return from `entry` to `exit`, from one security's bars and
    actions (S7.3).

    Trades fill at a session's open or close (app/backtest/schedule.py), so a holding
    runs from one of those prices to another, and its growth multiplies these legs:

    - From an open, close / open of the entry's session. That open is already ex-split
      and ex-dividend, so the leg needs neither.
    - For each later session through the last close before the exit, its daily total
      return, k_t * (close_t + div_t) / close_{t-1}, as `daily_total_returns` makes it.
    - To an open, k * (open + div) / close_{t-1}, with the exit session's split factor
      and dividend: whoever holds at the close before an ex-date gets its dividend.

    `bars` come oldest first and must include the entry's session, and `actions` are
    the same security's. Returns None if no trade could fill at the entry (`fills_at`).
    If none could at the exit either, because the bars end before it, as when a security
    stops trading, or nothing traded then, the holding is valued at its last close that
    traded instead, and the result isn't `complete`.

    Raises ValueError if the exit doesn't come after the entry, and for bars or actions
    that `daily_total_returns` rejects.
    """
    if _order(exit) <= _order(entry):
        raise ValueError(
            f"a holding's exit, {exit}, must come after its entry, {entry}"
        )
    _check_series("bars", bars)
    if not fills_at(bars, entry):
        return None
    by_session = {bar.session_date: bar for bar in bars}
    first = by_session[entry.session]
    splits, dividends = _by_ex_date(actions, first.security_id)

    # From the entry's price to its session's close, then close to close up to the
    # exit: through its session for a close, through the session before for an open.
    start = _price(first, "close") / _price(first, entry.price)
    held = [
        bar
        for bar in bars
        if entry.session <= bar.session_date
        and (
            bar.session_date <= exit.session
            if exit.price == "close"
            else bar.session_date < exit.session
        )
    ]
    held_actions = [
        action
        for action in actions
        if entry.session < action.ex_date <= held[-1].session_date
    ]
    daily = daily_total_returns(held, held_actions)

    final = by_session.get(exit.session)
    if (
        exit.price == "open"
        and final is not None
        and _traded(final)
        and _positive(final.open)
    ):
        previous = by_session[daily[-1].session_date] if daily else first
        split = round_split_factor(splits.get(exit.session, 1.0))
        dividend = dividends.get(exit.session, 0.0)
        growth = _compound(start, daily) * split
        growth *= (_price(final, "open") + dividend) / _price(previous, "close")
        return HoldingReturn(first.security_id, entry, exit, growth - 1, True)

    # Otherwise it's valued at its last close that traded: the exit's, if that's one.
    last = entry.session
    for day in daily:
        if _traded(by_session[day.session_date]):
            last = day.session_date
    growth = _compound(start, (day for day in daily if day.session_date <= last))
    if exit.price == "close" and last == exit.session:
        return HoldingReturn(first.security_id, entry, exit, growth - 1, True)
    return HoldingReturn(
        first.security_id,
        entry,
        PricePoint(last, "close"),
        growth - 1,
        complete=False,
    )


def total_returns_as_of(
    view: PointInTimeView,
    security: str | Security,
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
    and every row read is in its access log. `security` is a ticker, resolved at the
    knowledge time, or a `Security` the view gave (see `get_price_series_as_of`).
    """
    bars = view.get_price_series_as_of(security, start, end)
    actions = view.get_corporate_actions_as_of(security, start, end)
    return daily_total_returns(bars, actions)


def holding_return_as_of(
    view: PointInTimeView,
    security: str | Security,
    entry: PricePoint,
    exit: PricePoint,
) -> HoldingReturn | None:
    """`holding_return` from the bars and actions known at the view's knowledge time.

    The view must be bound at or after the close of the exit's session, when its bar
    became known (doc/reference/time-model.md, rule 4): a next-day open is read after
    that session's close. `security` is a ticker or a `Security`, as for
    `total_returns_as_of`. A `Security` that had stopped trading by then has no bars
    from the day it stopped on (`_until_stopped`). Raises ValueError for a view bound
    earlier.
    """
    _check_known(view, exit)
    bars = view.get_price_series_as_of(security, entry.session, exit.session)
    actions = view.get_corporate_actions_as_of(security, entry.session, exit.session)
    bars, actions = _until_stopped(security, bars, actions)
    return holding_return(bars, actions, entry, exit)


def fills_at_as_of(
    view: PointInTimeView, security: str | Security, point: PricePoint
) -> bool:
    """`fills_at` from the bars known at the view's knowledge time, which must be bound
    at or after the close of the point's session, as for `holding_return_as_of`. A
    `Security` that had stopped trading by the point's session doesn't fill there,
    whatever bars its vendor has. Raises ValueError for a view bound earlier."""
    _check_known(view, point)
    bars = view.get_price_series_as_of(security, point.session, point.session)
    bars, _ = _until_stopped(security, bars, [])
    return fills_at(bars, point)


def _until_stopped(
    security: str | Security,
    bars: Sequence[PriceBar],
    actions: Sequence[CorporateAction],
) -> tuple[list[PriceBar], list[CorporateAction]]:
    """The bars and actions from before the day `security` stopped trading, if it had
    by the knowledge time: `PointInTimeView.get_security` gives it with no ticker from
    that day, which app/data/sources/securities.toml dates from a filing. A vendor's bar
    from then on is a leftover, such as Tiingo's for Xilinx on February 14, 2022."""
    if (
        isinstance(security, str)
        or security.ticker is not None
        or security.effective_date is None
    ):
        return list(bars), list(actions)
    stopped = security.effective_date
    return (
        [bar for bar in bars if bar.session_date < stopped],
        [action for action in actions if action.ex_date < stopped],
    )


def _check_known(view: PointInTimeView, point: PricePoint) -> None:
    """Raise ValueError unless the view is bound at or after the close of `point`'s
    session, when its bar became known (doc/reference/time-model.md, rule 4)."""
    known = calendar.session_close(point.session)
    if view.knowledge_time < known:
        raise ValueError(
            f"the {point} is known only at {known.isoformat()}, after the view's "
            f"knowledge time {view.knowledge_time.isoformat()}"
        )


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


def _by_ex_date(
    actions: Sequence[CorporateAction], security_id: str | None
) -> tuple[dict[date, float], dict[date, float]]:
    """The split factors and the dividends of one security's actions, by ex-date.

    Raises ValueError for an action of a security other than `security_id`, an action
    of an unknown kind, and two of one kind on a day.
    """
    splits: dict[date, float] = {}
    dividends: dict[date, float] = {}
    for action in actions:
        if security_id is not None and action.security_id != security_id:
            raise ValueError(
                f"an action of {action.security_id} among {security_id}'s bars"
            )
        by_date = {"split": splits, "dividend": dividends}.get(action.action)
        if by_date is None:
            raise ValueError(f"unknown corporate action {action.action!r}")
        if action.ex_date in by_date:
            raise ValueError(f"two {action.action}s on {action.ex_date}")
        by_date[action.ex_date] = action.value
    return splits, dividends


def _order(point: PricePoint) -> tuple[date, int]:
    """Sorts price points in time: a session's open comes before its close."""
    return (point.session, 0 if point.price == "open" else 1)


def _price(bar: PriceBar, price: Literal["open", "close"]) -> float:
    """A bar's open or close, which the caller has checked is there."""
    value = bar.open if price == "open" else bar.close
    assert value is not None
    return value


def _positive(price: float | None) -> bool:
    """Whether a price is there and above zero, so a trade could get it."""
    return price is not None and price > 0


def _traded(bar: PriceBar) -> bool:
    """Whether anything traded in a bar's session: not if its volume is zero. A bar
    without a volume counts as traded."""
    return bar.volume != 0


def _compound(growth: float, daily: Iterable[DailyReturn]) -> float:
    """`growth` multiplied by 1 plus each daily return."""
    for day in daily:
        growth *= 1 + day.value
    return growth
