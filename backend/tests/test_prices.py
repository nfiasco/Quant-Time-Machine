from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.data.calendar import CalendarError
from app.data.errors import LookAheadError, NotFoundError
from app.data.records import PriceBar
from app.data.timeutil import parse_knowledge_time
from app.data.view import AccessRecord, PointInTimeView

# The fixture bars are made up (tests/fixtures/price_bars.csv): Tiingo's terms don't
# allow sharing its data.


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def view_at(store: Path, as_of: str) -> PointInTimeView:
    """A view of the fixture store at an `as_of`-style time (New York time)."""
    return PointInTimeView(parse_knowledge_time(as_of), store=store)


def latest_session(store: Path, as_of: str, ticker: str = "AAPL") -> date | None:
    with view_at(store, as_of) as view:
        bar = view.get_price_as_of(ticker)
    return None if bar is None else bar.session_date


def test_bar_known_only_after_close(fixture_store: Path) -> None:
    # At 09:30 ET on June 5, 2020, that day's bar isn't known until its 16:00 close.
    with view_at(fixture_store, "2020-06-05") as view:
        bar = view.get_price_as_of("AAPL")
        with pytest.raises(
            LookAheadError, match="AAPL's bar for 2020-06-05 isn't known until"
        ):
            view.get_price_as_of("AAPL", session=date(2020, 6, 5))

    assert bar is not None
    assert bar.session_date == date(2020, 6, 4)
    # Known at the close itself: the comparison is inclusive.
    assert latest_session(fixture_store, "2020-06-05T16:00") == date(2020, 6, 5)
    assert latest_session(fixture_store, "2020-06-05T15:59") == date(2020, 6, 4)


def test_a_bar_comes_back_under_the_tickers_identity(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-06-05") as view:
        bar = view.get_price_as_of("AAPL")

    assert bar == PriceBar(
        security_id="apple",
        ticker="AAPL",
        cik=320193,
        session_date=date(2020, 6, 4),
        open=102.5,
        high=103.5,
        low=101.5,
        close=102.0,
        volume=1_300_000,
        available_at=utc(2020, 6, 4, 20),  # 16:00 EDT
        time_assumed=False,
        source="tiingo",
        source_ref="made up: AAPL 2020-06-04",
    )


def test_a_weekend_sees_fridays_bar(fixture_store: Path) -> None:
    assert latest_session(fixture_store, "2020-06-06") == date(2020, 6, 5)
    assert latest_session(fixture_store, "2020-06-07T20:00") == date(2020, 6, 5)


def test_a_holiday_sees_the_previous_sessions_bar(fixture_store: Path) -> None:
    # The NYSE was closed on Friday, July 3, 2020, for Independence Day.
    assert latest_session(fixture_store, "2020-07-03") == date(2020, 7, 2)
    with (
        view_at(fixture_store, "2020-07-07") as view,
        pytest.raises(CalendarError, match="not a NYSE trading session"),
    ):
        view.get_price_as_of("AAPL", session=date(2020, 7, 3))


def test_an_early_close_bar_is_known_at_1300(fixture_store: Path) -> None:
    # The day after Thanksgiving 2020, the NYSE closed at 13:00 ET.
    assert latest_session(fixture_store, "2020-11-27T13:00") == date(2020, 11, 27)
    assert latest_session(fixture_store, "2020-11-27T12:59") == date(2020, 11, 25)


def test_a_given_session_is_read_once_it_has_closed(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-07-07") as view:
        july_2 = view.get_price_as_of("AAPL", session=date(2020, 7, 2))
        # A session with no stored bar reads as nothing known.
        june_8 = view.get_price_as_of("AAPL", session=date(2020, 6, 8))

    assert july_2 is not None
    assert (july_2.session_date, july_2.close) == (date(2020, 7, 2), 110.5)
    assert june_8 is None


def test_before_the_first_bar_nothing_is_known(fixture_store: Path) -> None:
    assert latest_session(fixture_store, "2020-06-01") is None


def test_fb_in_2020_reads_facebooks_bars(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-06-05T16:00") as view:
        bar = view.get_price_as_of("FB")
        with pytest.raises(NotFoundError, match="unknown ticker: META"):
            view.get_price_as_of("META")  # Facebook switched to META in 2022

    assert bar is not None
    assert (bar.security_id, bar.ticker, bar.cik) == ("meta", "FB", 1326801)
    assert (bar.session_date, bar.close) == (date(2020, 6, 5), 233.5)


def test_an_unknown_ticker_is_not_found(fixture_store: Path) -> None:
    with (
        view_at(fixture_store, "2020-06-05") as view,
        pytest.raises(NotFoundError, match="unknown ticker: NOPE"),
    ):
        view.get_price_history_as_of("NOPE", 5)


def test_the_history_ends_at_the_last_closed_session(fixture_store: Path) -> None:
    def history(as_of: str, lookback: int) -> list[date]:
        with view_at(fixture_store, as_of) as view:
            return [
                b.session_date for b in view.get_price_history_as_of("AAPL", lookback)
            ]

    june = [date(2020, 6, day) for day in range(1, 6)]
    assert history("2020-06-05", 3) == june[1:4]  # oldest first; June 5 isn't known
    assert history("2020-06-05T16:00", 3) == june[2:5]
    assert history("2020-06-03", 10) == june[:2]  # only what's known so far
    # July 3 had no session, so the window skips it rather than filling it.
    assert history("2020-07-07", 2) == [date(2020, 7, 2), date(2020, 7, 6)]


def test_the_lookback_must_be_positive(fixture_store: Path) -> None:
    with (
        view_at(fixture_store, "2020-06-05") as view,
        pytest.raises(ValueError, match="at least 1 session"),
    ):
        view.get_price_history_as_of("AAPL", 0)


def test_a_future_row_never_reaches_a_read(fixture_store: Path) -> None:
    # The fixture's canary version of June 5's bar (999) is known only in 2099.
    with view_at(fixture_store, "2098-12-31") as view:
        bar = view.get_price_as_of("AAPL", session=date(2020, 6, 5))
        history = view.get_price_history_as_of("AAPL", 100)

    assert bar is not None
    assert bar.close == 103.8
    assert all(b.close != 999.0 for b in history)


def test_reads_are_in_the_access_log(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-06-05") as view:
        view.get_price_as_of("AAPL")

        assert view.access_log == (
            AccessRecord(
                table="securities",
                key=("apple",),
                available_at=utc(2007, 1, 9, 5),  # Apple Inc. since 2007-01-09
                source_ref="https://www.sec.gov/Archives/edgar/data/320193/000110465907001648/a07-1512_18k.htm",
            ),
            AccessRecord(
                table="price_bars",
                key=("apple", date(2020, 6, 4)),
                available_at=utc(2020, 6, 4, 20),
                source_ref="made up: AAPL 2020-06-04",
            ),
        )
