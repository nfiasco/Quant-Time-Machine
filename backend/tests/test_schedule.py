import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any

import pytest

from app.backtest.schedule import (
    Rebalance,
    ScheduleError,
    decision_times,
    rebalance,
    rebalances,
)
from app.backtest.spec import ExperimentSpec, parse_spec
from app.data import calendar
from app.data.errors import LookAheadError
from app.data.store import write_rows
from app.data.tables import PRICE_BARS
from app.data.timeutil import ET, market_time
from app.data.view import PointInTimeView

CANONICAL = Path(__file__).parent / "fixtures" / "specs" / "canonical.json"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def new_york(day: date, hour: int, minute: int = 0) -> datetime:
    """A New York wall-clock time, as an instant."""
    return market_time(day, time(hour, minute))


def spec(start: str | None = None, **schedule: Any) -> ExperimentSpec:
    """The canonical spec (roadmap §3.4), with another start, or some of its schedule
    changed."""
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    if start is not None:
        data["period"]["start"] = start
    data["schedule"].update(schedule)
    return parse_spec(data)


def test_fill_strictly_after_decision(fixture_store: Path) -> None:
    # The golden case (doc/time-model.md, rule 10): a decision at 09:30 ET on Monday,
    # June 1, 2020 fills at that day's 16:00 close.
    june_1 = date(2020, 6, 1)
    decided = rebalance(utc(2020, 6, 1, 13, 30))
    assert decided == Rebalance(
        utc(2020, 6, 1, 13, 30), utc(2020, 6, 1, 20), june_1, "close"
    )

    # The decision sees bars through Friday, May 29 only. Made-up bars, as in the
    # fixtures, which start on June 1.
    write_rows(
        fixture_store,
        PRICE_BARS,
        [
            {
                "security_id": "apple",
                "session_date": day,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1000,
                "source": "tiingo",
                "source_ref": f"made up: AAPL {day}",
                "available_at": calendar.session_close(day),
                "time_assumed": False,
            }
            for day, close in ((date(2020, 5, 28), 98.0), (date(2020, 5, 29), 99.0))
        ],
    )
    with PointInTimeView(decided.decision_time, store=fixture_store) as view:
        seen = view.get_price_as_of("AAPL")
        with pytest.raises(LookAheadError):
            view.get_price_as_of("AAPL", session=june_1)
    with PointInTimeView(decided.fill_time, store=fixture_store) as view:
        traded = view.get_price_as_of("AAPL", session=june_1)
    assert seen is not None and seen.session_date == date(2020, 5, 29)
    assert traded is not None and traded.close == 100.5  # known at the fill itself

    # Every month since 2005, through holidays and early closes, by both rules.
    early_closes = []
    for at, fills in (
        (time(9, 30), ("same_day_close", "next_day_open")),
        (time(16), ("next_day_open",)),
    ):
        for decision in decision_times(date(2005, 1, 1), date(2026, 12, 31), at):
            day = decision.astimezone(ET).date()
            for fill in fills:
                filled = rebalance(decision, fill)
                assert filled.decision_time == decision
                assert filled.fill_time > filled.decision_time
                if fill == "same_day_close":
                    assert filled.fill_session == day
                    assert filled.fill_time == calendar.session_close(day)
                    if filled.fill_time.astimezone(ET).hour == 13:
                        early_closes.append(day)
                else:
                    assert filled.fill_session == calendar.next_session(day)
                    assert filled.fill_time == calendar.session_open(
                        filled.fill_session
                    )
    assert early_closes == [date(2006, 7, 3), date(2017, 7, 3), date(2023, 7, 3)]


def test_a_1600_decision_cannot_fill_at_that_close() -> None:
    decision = new_york(date(2020, 6, 1), 16)

    with pytest.raises(ScheduleError, match="isn't before that day's close, at 16:00"):
        rebalance(decision, "same_day_close")
    # Its earliest fill is the next session's open.
    assert rebalance(decision, "next_day_open") == Rebalance(
        decision, utc(2020, 6, 2, 13, 30), date(2020, 6, 2), "open"
    )
    # A minute earlier, it fills at the close.
    assert rebalance(new_york(date(2020, 6, 1), 15, 59)).fill_time == utc(
        2020, 6, 1, 20
    )


def test_an_early_close_day_fills_at_1300() -> None:
    # Monday, July 3, 2023 was July's first trading day, and the NYSE closed at 13:00 ET.
    july_3 = date(2023, 7, 3)

    (decision,) = decision_times(date(2023, 7, 1), date(2023, 7, 31))
    assert rebalance(decision) == Rebalance(
        utc(2023, 7, 3, 13, 30), utc(2023, 7, 3, 17), july_3, "close"
    )
    # A 13:00 decision that day is at the close itself, so it can't fill there.
    with pytest.raises(ScheduleError, match="at 13:00 ET on 2023-07-03 isn't before"):
        rebalance(new_york(july_3, 13))


def test_november_2012_after_hurricane_sandy() -> None:
    # The NYSE closed on October 29 and 30, 2012, and reopened on Wednesday, October 31.
    # November's first trading day was Thursday, November 1, still in daylight time.
    october, november = decision_times(date(2012, 10, 1), date(2012, 11, 30))
    assert (october, november) == (utc(2012, 10, 1, 13, 30), utc(2012, 11, 1, 13, 30))

    assert rebalance(november) == Rebalance(
        november, utc(2012, 11, 1, 20), date(2012, 11, 1), "close"
    )
    assert rebalance(november, "next_day_open") == Rebalance(
        november, utc(2012, 11, 2, 13, 30), date(2012, 11, 2), "open"
    )
    # The next day's open after Friday, October 26 was October 31's.
    friday = new_york(date(2012, 10, 26), 9, 30)
    assert rebalance(friday, "next_day_open") == Rebalance(
        friday, utc(2012, 10, 31, 13, 30), date(2012, 10, 31), "open"
    )
    with pytest.raises(ScheduleError, match="2012-10-29 had no trading session"):
        rebalance(new_york(date(2012, 10, 29), 9, 30))


def test_the_canonical_specs_schedule() -> None:
    schedule = rebalances(spec())

    assert len(schedule) == 192  # every month from January 2010 to December 2025
    first, last = schedule[0], schedule[-1]
    assert (first.decision_time, first.fill_time) == (
        utc(2010, 1, 4, 14, 30),  # 09:30 EST on Monday, January 4, 2010
        utc(2010, 1, 4, 21),
    )
    assert last.decision_time == utc(2025, 12, 1, 14, 30)
    assert {r.fill_price for r in schedule} == {"close"}


def test_a_decision_after_early_closes_names_them() -> None:
    decision = "first_trading_day 13:30 America/New_York"
    late = spec(start="2005-01-01", decision=decision)

    with pytest.raises(ScheduleError) as raised:
        rebalances(late)
    assert str(raised.value) == (
        "schedule.decision must be before the close for a same_day_close fill, but "
        "the market closed before 13:30 ET on 2006-07-03, 2017-07-03, and 2023-07-03. "
        "Decide earlier, or use next_day_open."
    )
    # Filled at the next day's open, the same decisions are fine.
    next_open = spec(start="2005-01-01", decision=decision, fill="next_day_open")
    assert len(rebalances(next_open)) == 252  # every month from 2005 to 2025


def test_a_rebalance_never_fills_at_its_decision() -> None:
    with pytest.raises(ScheduleError, match="isn't after its decision"):
        Rebalance(utc(2020, 6, 1, 20), utc(2020, 6, 1, 20), date(2020, 6, 1), "close")


def test_naive_decision_times_are_rejected() -> None:
    naive = datetime(2020, 6, 1, 9, 30)  # noqa: DTZ001 (naive on purpose)

    with pytest.raises(ValueError, match="naive"):
        rebalance(naive)
