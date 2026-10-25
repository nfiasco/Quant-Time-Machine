"""Time helpers: the market clock, the knowledge-time parser, and how people read times.

The rules are in doc/time-model.md:

- Rule 1: instants are timezone-aware and compared in UTC. A naive datetime is a bug.
- Rule 3: a knowledge time given as a bare date means 09:30 ET on that date. A timestamp
  with an offset is used as given, and one without an offset is New York wall-clock time,
  unless it falls in a daylight-saving change, where it has no single meaning.
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
"""The market clock (rule 2)."""

MARKET_OPEN = time(9, 30)
"""What a bare date means, and the default decision time (rules 3 and 9)."""

# YYYY-MM-DD, optionally followed by THH:MM[:SS[.ffffff]] and then Z or ±HH:MM.
# Stricter than datetime.fromisoformat, which also takes week dates and 20200605.
_KNOWLEDGE_TIME = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})"
    r"(?:T(?P<time>\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?)(?P<offset>Z|[+-]\d{2}:\d{2})?)?",
    re.ASCII,
)

_EXPECTED = (
    "Use a date such as 2020-06-05 (9:30 AM ET that day), a New York time such as "
    "2020-06-05T09:30, or a time with an offset such as 2020-06-05T13:30Z."
)

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class KnowledgeTimeError(ValueError):
    """A knowledge time (`as_of`) that can't be turned into an exact instant."""


def to_utc(value: datetime) -> datetime:
    """Return `value` as an aware datetime in UTC. A naive datetime raises ValueError (rule 1)."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"naive datetime {value.isoformat()} has no time zone")
    return value.astimezone(UTC)


def market_time(day: date, at: time) -> datetime:
    """The UTC instant of a New York wall-clock time: 09:30 on 2020-06-05 is 13:30Z.

    In the fall-back hour a wall-clock time happens twice, and the later instant wins,
    so the system errs toward knowing less (rule 11). A time skipped by the
    spring-forward change never happened, so it raises KnowledgeTimeError.
    """
    wall = datetime.combine(day, at.replace(tzinfo=None))
    instant = wall.replace(tzinfo=ET, fold=1).astimezone(UTC)
    if instant.astimezone(ET).replace(tzinfo=None) != wall:
        raise KnowledgeTimeError(
            f"{wall:%Y-%m-%d %H:%M} doesn't exist in New York: clocks skipped that hour"
        )
    return instant


def parse_knowledge_time(text: str) -> datetime:
    """Parse a knowledge time (the API's `as_of`) into an aware UTC datetime.

    - `2020-06-05` means 09:30 ET that day (13:30Z), even on a weekend or holiday.
    - `2020-06-05T09:30` (no offset) is New York time: also 13:30Z.
    - `2020-06-05T13:30Z` or `2020-06-05T09:30-04:00` (with an offset) is used as given.

    Anything else raises KnowledgeTimeError, whose message is a sentence a person can
    act on. That includes a New York time in a daylight-saving change, which never
    happened or happened twice.
    """
    match = _KNOWLEDGE_TIME.fullmatch(text)
    if match is None:
        message = f"{text!r} isn't a knowledge time. {_EXPECTED}"
        if " " in text and _KNOWLEDGE_TIME.fullmatch(text.replace(" ", "+")):
            message += " A '+' in a URL arrives as a space, so encode it as %2B."
        raise KnowledgeTimeError(message)

    try:
        day = date.fromisoformat(match["date"])
        if match["time"] is None:
            return market_time(day, MARKET_OPEN)
        if match["offset"] is None:
            return _new_york_time(day, time.fromisoformat(match["time"]))
        return to_utc(datetime.fromisoformat(text))
    except KnowledgeTimeError:
        raise
    except (ValueError, OverflowError) as error:
        # For example February 30, hour 25, or an offset that pushes the year out of range.
        raise KnowledgeTimeError(
            f"{text!r} isn't a real date or time: {error}."
        ) from None


def _new_york_time(day: date, at: time) -> datetime:
    """The instant of a New York wall-clock time that a person gave as a knowledge time.

    US clocks change at 2:00 AM, so in spring 02:00-02:59 never happens, and in the fall
    01:00-01:59 happens twice. Neither has one meaning, so both raise KnowledgeTimeError
    asking for an offset. (Ingestion's `market_time` takes the later of the two repeated
    instants instead, following rule 11.)
    """
    wall = datetime.combine(day, at)
    first, second = (wall.replace(tzinfo=ET, fold=fold) for fold in (0, 1))
    before, after = first.utcoffset(), second.utcoffset()
    if before == after:
        return to_utc(first)
    assert before is not None and after is not None
    when = f"{_clock(at)} on {_day(day)}"
    if before < after:
        raise KnowledgeTimeError(
            f"{when} never happened in New York: clocks jumped from 2:00 to 3:00 AM. "
            "Add an offset, or choose another time."
        )
    raise KnowledgeTimeError(
        f"{when} happened twice in New York: clocks went back from 2:00 to 1:00 AM. "
        f"Add an offset to pick one: {_offset(before)} for the first, "
        f"{_offset(after)} for the second."
    )


def describe_time(instant: datetime) -> str:
    """An instant as people read market times: "June 5, 2020, 9:30 AM ET".

    For sentences shown as they are, such as an API response's `reason`. Seconds appear
    only when they aren't zero, as in "April 30, 2020, 6:03:10 PM ET".
    """
    local = to_utc(instant).astimezone(ET)
    return f"{_day(local.date())}, {_clock(local.time())} ET"


def _day(day: date) -> str:
    """For example "June 5, 2020"."""
    return f"{_MONTHS[day.month - 1]} {day.day}, {day.year}"


def _clock(at: time) -> str:
    """For example "9:30 AM", or "6:03:10 PM" when there are seconds."""
    text = f"{at.hour % 12 or 12}:{at.minute:02d}"
    if at.second:
        text += f":{at.second:02d}"
    return f"{text} {'AM' if at.hour < 12 else 'PM'}"


def _offset(offset: timedelta) -> str:
    """A UTC offset as ISO 8601 writes it: -04:00."""
    minutes = int(offset.total_seconds()) // 60
    sign = "-" if minutes < 0 else "+"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"
