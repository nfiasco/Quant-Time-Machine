"""The NYSE trading calendar (S3.5; doc/time-model.md, rule 2).

A thin wrapper around exchange_calendars' XNYS calendar, which knows holidays, early
closes, and unscheduled closures such as Hurricane Sandy. Never work out trading days
from weekdays; use these functions.

Days are New York session dates (`datetime.date`), and instants are aware UTC datetimes.
The calendar covers 1970 through one year from today. Outside that range, and for a
day that isn't a session where one is required, functions raise CalendarError.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from functools import cache

import exchange_calendars as xcals
from exchange_calendars.errors import (
    DateOutOfBounds,
    NotSessionError,
    RequestedSessionOutOfBounds,
)

from app.data.timeutil import to_utc

CALENDAR_START = date(1970, 1, 1)
"""The first day the calendar covers. exchange_calendars defaults to only the last 20
years, which would miss 2005 prices and 1990s macro data. A day before the calendar's
first session raises, so the start sits well before any date we use."""


class CalendarError(ValueError):
    """A day the calendar can't answer for: not a session, or outside its range."""


@cache
def _xnys() -> xcals.ExchangeCalendar:
    return xcals.get_calendar("XNYS", start=CALENDAR_START.isoformat())


@contextmanager
def _plain_errors(*days: date) -> Iterator[None]:
    """Check the arguments, and turn the library's errors into CalendarError."""
    for day in days:
        # datetime is a subclass of date, and passing one usually means a time-zone mix-up.
        if isinstance(day, datetime) or not isinstance(day, date):
            raise TypeError(f"expected a datetime.date, got {day!r}")
    try:
        yield
    except NotSessionError:
        raise CalendarError(f"{days[0]} is not a NYSE trading session") from None
    except DateOutOfBounds, RequestedSessionOutOfBounds:
        calendar = _xnys()
        first, last = calendar.first_session.date(), calendar.last_session.date()
        raise CalendarError(
            f"{', '.join(map(str, days))}: outside the calendar, "
            f"which runs from {first} to {last}"
        ) from None


def is_session(day: date) -> bool:
    """Whether the NYSE held a session on `day`. Weekends, holidays, and closures didn't."""
    with _plain_errors(day):
        return bool(_xnys().is_session(day))


def session_open(day: date) -> datetime:
    """When the session on `day` opened, in UTC (09:30 ET)."""
    with _plain_errors(day):
        return to_utc(_xnys().session_open(day).to_pydatetime())


def session_close(day: date) -> datetime:
    """When the session on `day` closed, in UTC: 16:00 ET, or 13:00 ET on an early close.

    A daily bar becomes known at this instant (rule 4).
    """
    with _plain_errors(day):
        return to_utc(_xnys().session_close(day).to_pydatetime())


def previous_session(day: date) -> date:
    """The last session strictly before `day`. `day` doesn't have to be a session."""
    with _plain_errors(day):
        calendar = _xnys()
        if calendar.is_session(day):
            return calendar.previous_session(day).date()
        return calendar.date_to_session(day, direction="previous").date()


def next_session(day: date) -> date:
    """The first session strictly after `day`. `day` doesn't have to be a session."""
    with _plain_errors(day):
        calendar = _xnys()
        if calendar.is_session(day):
            return calendar.next_session(day).date()
        return calendar.date_to_session(day, direction="next").date()


def first_trading_day(year: int, month: int) -> date:
    """The first session of a month, the default decision day (rule 9)."""
    first = date(year, month, 1)
    with _plain_errors(first):
        return _xnys().date_to_session(first, direction="next").date()


def sessions_between(start: date, end: date) -> list[date]:
    """Every session from `start` through `end`, inclusive."""
    with _plain_errors(start, end):
        return [session.date() for session in _xnys().sessions_in_range(start, end)]
