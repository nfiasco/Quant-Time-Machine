from datetime import UTC, date, datetime

import pytest

from app.data.calendar import (
    CalendarError,
    first_trading_day,
    is_session,
    next_session,
    previous_session,
    session_close,
    session_open,
    sessions_between,
)
from app.data.timeutil import MARKET_OPEN, market_time


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_calendar_closures_and_early_closes() -> None:
    # Hurricane Sandy closed the market for two days.
    assert not is_session(date(2012, 10, 29))
    assert not is_session(date(2012, 10, 30))
    assert is_session(date(2012, 10, 31))
    # National days of mourning for George H. W. Bush and Jimmy Carter.
    assert not is_session(date(2018, 12, 5))
    assert not is_session(date(2025, 1, 9))
    # Good Friday is an exchange holiday, though not a federal one.
    assert not is_session(date(2020, 4, 10))
    # The day after Thanksgiving closes at 13:00 ET.
    assert session_close(date(2020, 11, 27)) == utc(2020, 11, 27, 18)


def test_regular_session_times_follow_daylight_saving() -> None:
    assert session_open(date(2020, 6, 4)) == utc(2020, 6, 4, 13, 30)
    assert session_close(date(2020, 6, 4)) == utc(2020, 6, 4, 20)  # 16:00 EDT
    assert session_close(date(2020, 1, 15)) == utc(2020, 1, 15, 21)  # 16:00 EST


def test_weekends_are_not_sessions() -> None:
    assert not is_session(date(2020, 6, 6))
    assert not is_session(date(2020, 6, 7))
    assert is_session(date(2020, 6, 8))


def test_previous_and_next_session_skip_closures() -> None:
    assert previous_session(date(2012, 10, 31)) == date(2012, 10, 26)
    assert next_session(date(2012, 10, 26)) == date(2012, 10, 31)
    # The day itself needn't be a session.
    assert previous_session(date(2012, 10, 30)) == date(2012, 10, 26)
    assert next_session(date(2012, 10, 29)) == date(2012, 10, 31)
    # Across a weekend.
    assert previous_session(date(2020, 6, 8)) == date(2020, 6, 5)
    assert next_session(date(2020, 6, 5)) == date(2020, 6, 8)


@pytest.mark.parametrize(
    ("year", "month", "expected", "decision_time"),
    [
        (2020, 6, date(2020, 6, 1), utc(2020, 6, 1, 13, 30)),
        (2020, 7, date(2020, 7, 1), utc(2020, 7, 1, 13, 30)),
        # Markets reopened on October 31 after Hurricane Sandy.
        (2012, 11, date(2012, 11, 1), utc(2012, 11, 1, 13, 30)),
        # January 1 is a holiday, and January 2 and 3 were a weekend.
        (2021, 1, date(2021, 1, 4), utc(2021, 1, 4, 14, 30)),
    ],
)
def test_first_trading_day_of_month(
    year: int, month: int, expected: date, decision_time: datetime
) -> None:
    day = first_trading_day(year, month)

    assert day == expected
    assert market_time(day, MARKET_OPEN) == decision_time


def test_sessions_between_is_inclusive() -> None:
    assert sessions_between(date(2012, 10, 25), date(2012, 11, 1)) == [
        date(2012, 10, 25),
        date(2012, 10, 26),
        date(2012, 10, 31),
        date(2012, 11, 1),
    ]


def test_dates_in_1990_are_covered() -> None:
    assert first_trading_day(1990, 1) == date(1990, 1, 2)
    assert is_session(date(1990, 2, 2))


def test_session_times_need_a_session() -> None:
    with pytest.raises(CalendarError, match="not a NYSE trading session"):
        session_close(date(2012, 10, 29))


def test_dates_outside_the_calendar_raise() -> None:
    with pytest.raises(CalendarError, match="outside the calendar"):
        is_session(date(1960, 1, 4))


def test_datetimes_are_rejected() -> None:
    with pytest.raises(TypeError, match=r"datetime\.date"):
        is_session(utc(2020, 6, 4))
