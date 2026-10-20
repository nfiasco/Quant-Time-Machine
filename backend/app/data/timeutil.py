"""Time helpers: the market clock and the knowledge-time parser.

The rules are in doc/time-model.md:

- Rule 1: instants are timezone-aware and compared in UTC. A naive datetime is a bug.
- Rule 3: a knowledge time given as a bare date means 09:30 ET on that date. A timestamp
  with an offset is used as given, and one without an offset is New York wall-clock time.
"""

import re
from datetime import UTC, date, datetime, time
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
    "expected a date such as 2020-06-05 (09:30 ET), a New York time such as "
    "2020-06-05T09:30, or a timestamp with an offset such as 2020-06-05T13:30Z"
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

    Anything else raises KnowledgeTimeError.
    """
    match = _KNOWLEDGE_TIME.fullmatch(text)
    if match is None:
        message = f"{_EXPECTED}; got {text!r}"
        if " " in text and _KNOWLEDGE_TIME.fullmatch(text.replace(" ", "+")):
            message += (
                ". A '+' in a URL query string arrives as a space, so encode it as %2B"
            )
        raise KnowledgeTimeError(message)

    try:
        day = date.fromisoformat(match["date"])
        if match["time"] is None:
            return market_time(day, MARKET_OPEN)
        if match["offset"] is None:
            return market_time(day, time.fromisoformat(match["time"]))
        return to_utc(datetime.fromisoformat(text))
    except KnowledgeTimeError:
        raise
    except (ValueError, OverflowError) as error:
        # For example February 30, hour 25, or an offset that pushes the year out of range.
        raise KnowledgeTimeError(f"{text!r} is not a valid time: {error}") from None
