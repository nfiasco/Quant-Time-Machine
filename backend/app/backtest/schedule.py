"""Rebalance decisions and when their trades fill (S7.2; doc/reference/time-model.md, rules 9 and
10).

Decisions fall on the first trading day of each month, at a New York time: 09:30 by
default, when a decision sees prices through the previous session's close. A fill
always comes strictly after its decision, so a decision never sees the price it trades
at. A spec chooses one of two fill rules:

- `same_day_close`, the default (D5), fills at the decision day's close: 16:00 ET, or
  13:00 on an early-close day such as Monday, July 3, 2023, the first trading day of
  that July. A decision at or after the close can't fill at it, and raises
  ScheduleError.
- `next_day_open` fills at the next session's open, 09:30 ET.

A fill's price comes from the fill session's bar, which becomes known only at that
session's close (rule 4). So the simulation (S7.3) reads a next-day open after the
fill, never at the decision.
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal

from app.backtest.spec import ExperimentSpec, FillRule
from app.data import calendar
from app.data.timeutil import ET, MARKET_OPEN, market_time, to_utc


class ScheduleError(ValueError):
    """A decision that can't be made, or whose trades can't fill by the spec's rule."""


@dataclass(frozen=True)
class Rebalance:
    """A decision, and when its trades fill."""

    decision_time: datetime
    """When the decision is made, in UTC. It sees only what was known by then."""
    fill_time: datetime
    """When its trades fill, in UTC: always after `decision_time`."""
    fill_session: date
    fill_price: Literal["open", "close"]
    """Which of the fill session's prices the trades get."""

    def __post_init__(self) -> None:
        if self.fill_time <= self.decision_time:
            raise ScheduleError(
                f"a fill at {self.fill_time.isoformat()} isn't after its decision at "
                f"{self.decision_time.isoformat()}"
            )


def decision_times(start: date, end: date, at: time = MARKET_OPEN) -> list[datetime]:
    """The first trading day of each month from `start` through `end`, at `at` New York
    time, in UTC.

    From 2012-10-01 through 2012-11-30, they're October 1 and November 1 at 09:30 ET;
    the market had reopened on October 31, after Hurricane Sandy closed it for two days.
    """
    decisions = []
    year, month = start.year, start.month
    while (day := calendar.first_trading_day(year, month)) <= end:
        if day >= start:
            decisions.append(market_time(day, at))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return decisions


def rebalance(decision_time: datetime, fill: FillRule = "same_day_close") -> Rebalance:
    """A decision at `decision_time`, an aware datetime, and when its trades fill by
    the rule `fill`.

    Raises ScheduleError if the decision's day, in New York, had no session, or if the
    same day's close wouldn't come after the decision: a decision at 16:00, or at 13:00
    on an early-close day.
    """
    decision_time = to_utc(decision_time)
    local = decision_time.astimezone(ET)
    day = local.date()
    if not calendar.is_session(day):
        raise ScheduleError(f"{day} had no trading session, so no decision falls on it")
    if fill == "same_day_close":
        close = calendar.session_close(day)
        if close <= decision_time:
            raise ScheduleError(
                f"The decision at {local:%H:%M} ET on {day} isn't before that day's "
                f"close, at {close.astimezone(ET):%H:%M} ET, so its trades can't fill "
                "at that close. Decide earlier, or use next_day_open."
            )
        return Rebalance(decision_time, close, day, "close")
    session = calendar.next_session(day)
    return Rebalance(decision_time, calendar.session_open(session), session, "open")


def rebalances(spec: ExperimentSpec) -> list[Rebalance]:
    """Every decision of a spec's schedule over its period, with its fill.

    Raises one ScheduleError, naming every date, if a same-day close fill can't come
    after some of the decisions: a 13:30 decision fails on early-close days, such as
    July 3 in 2006, 2017, and 2023.
    """
    schedule, period = spec.schedule, spec.period
    found, too_late = [], []
    for decision in decision_times(period.start, period.end, schedule.decision_time):
        try:
            found.append(rebalance(decision, schedule.fill))
        except ScheduleError:
            too_late.append(decision.astimezone(ET).date().isoformat())
    if too_late:
        days = (
            f"{', '.join(too_late[:-1])}, and {too_late[-1]}"
            if len(too_late) > 2
            else " and ".join(too_late)
        )
        raise ScheduleError(
            "schedule.decision must be before the close for a same_day_close fill, "
            f"but the market closed before {schedule.decision_time:%H:%M} ET on "
            f"{days}. Decide earlier, or use next_day_open."
        )
    return found
