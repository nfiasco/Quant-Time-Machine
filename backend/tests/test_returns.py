from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.backtest.returns import (
    daily_total_returns,
    monthly_total_returns,
    round_split_factor,
    total_returns_as_of,
)
from app.data import calendar
from app.data.records import CorporateAction, PriceBar
from app.data.timeutil import parse_knowledge_time
from app.data.view import AccessRecord, PointInTimeView

# Every price here is made up, as in tests/fixtures/price_bars.csv: Tiingo's terms don't
# allow sharing its data. In the fixtures, Apple's August 2020 bars fall on its $0.82
# dividend (August 7) and its 4-for-1 split (August 31). How these returns compare
# with Tiingo's own adjusted closes is in tests/test_returns_vs_tiingo.py.


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def bar(day: date, close: float | None, security_id: str = "test") -> PriceBar:
    """A made-up bar, known at its session's close."""
    return PriceBar(
        security_id=security_id,
        ticker="TEST",
        cik=None,
        session_date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        available_at=calendar.session_close(day),
        time_assumed=False,
        source="test",
        source_ref=f"made up: {day}",
    )


def action(
    day: date, kind: str, value: float, security_id: str = "test"
) -> CorporateAction:
    """A made-up split or dividend, known at its ex-date's close."""
    return CorporateAction(
        security_id=security_id,
        ticker="TEST",
        cik=None,
        ex_date=day,
        action=kind,
        value=value,
        available_at=calendar.session_close(day),
        time_assumed=False,
        source="test",
        source_ref=f"made up: {kind} on {day}",
    )


def view_at(store: Path, as_of: str) -> PointInTimeView:
    """A view of the fixture store at an `as_of`-style time (New York time)."""
    return PointInTimeView(parse_knowledge_time(as_of), store=store)


JUNE_1, JUNE_2, JUNE_3 = date(2020, 6, 1), date(2020, 6, 2), date(2020, 6, 3)


@pytest.mark.parametrize(
    ("factor", "rounded"),
    [
        (7.000007, 7.0),  # Apple's 7-for-1, 2014
        (1.49999925, 1.5),  # NVIDIA's 3-for-2, 2007
        (1.3333333333, 4 / 3),  # Activision's 4-for-3, 2005
        (0.1, 0.1),  # Citigroup's 1-for-10, 2011
        (0.3333333333, 1 / 3),  # Time Warner's 1-for-3, 2009
        (20.0, 20.0),  # Amazon's 20-for-1, 2022
        (1.046, 1.046),  # IBM's Kyndryl spin-off, 2021: no simple ratio, kept
        (1.054, 1.054),  # Pfizer's Viatris spin-off, 2020
    ],
)
def test_split_factors_round_to_simple_ratios(factor: float, rounded: float) -> None:
    assert round_split_factor(factor) == rounded


@pytest.mark.parametrize("factor", [0.0, -2.0, float("nan"), float("inf")])
def test_split_factors_must_be_positive(factor: float) -> None:
    with pytest.raises(ValueError, match="positive number"):
        round_split_factor(factor)


def test_a_dividend_is_reinvested_on_its_ex_date() -> None:
    (june_2,) = daily_total_returns(
        [bar(JUNE_1, 100.0), bar(JUNE_2, 99.0)], [action(JUNE_2, "dividend", 2.0)]
    )

    assert june_2.value == pytest.approx(0.01)  # (99 + 2) / 100 - 1
    assert (june_2.dividend, june_2.split_factor) == (2.0, 1.0)
    assert june_2.previous_session == JUNE_1
    assert june_2.available_at == utc(2020, 6, 2, 20)  # known at the close, 16:00 ET


@pytest.mark.parametrize(
    ("before", "after", "factor", "expected"),
    [
        (500.0, 130.0, 4.0, 0.04),  # 4 * 130 / 500 - 1
        (700.0, 100.0, 7.000007, 0.0),  # rounded to 7, the split alone moves nothing
        (4.0, 44.0, 0.1, 0.1),  # a 1-for-10 reverse split: 0.1 * 44 / 4 - 1
        (126.0, 120.0, 1.046, 1.046 * 120 / 126 - 1),  # a spin-off's factor, as given
    ],
)
def test_a_split_scales_the_close(
    before: float, after: float, factor: float, expected: float
) -> None:
    (june_2,) = daily_total_returns(
        [bar(JUNE_1, before), bar(JUNE_2, after)], [action(JUNE_2, "split", factor)]
    )

    assert june_2.value == pytest.approx(expected, abs=1e-12)
    assert june_2.split_factor == round_split_factor(factor)


def test_a_missing_bar_makes_a_gap() -> None:
    bars = [bar(JUNE_1, 100.0), bar(JUNE_3, 102.0)]
    # A bar without a close counts as missing too.
    with_empty_bar = [bar(JUNE_1, 100.0), bar(JUNE_2, None), bar(JUNE_3, 102.0)]

    for series in (bars, with_empty_bar):
        (june_3,) = daily_total_returns(series, [])
        assert (june_3.previous_session, june_3.value) == (JUNE_1, pytest.approx(0.02))


def test_hurricane_sandys_closure_is_not_a_gap() -> None:
    # The market was closed on October 29 and 30, 2012, so the first session after
    # Friday, October 26 was Wednesday, October 31.
    friday, wednesday = date(2012, 10, 26), date(2012, 10, 31)

    (returned,) = daily_total_returns([bar(friday, 50.0), bar(wednesday, 51.0)], [])

    assert returned.previous_session == friday == calendar.previous_session(wednesday)
    assert returned.value == pytest.approx(0.02)


def test_actions_up_to_the_first_bar_are_ignored() -> None:
    # The first bar has no return of its own, so its split belongs to a return before
    # the series.
    (june_2,) = daily_total_returns(
        [bar(JUNE_1, 25.0), bar(JUNE_2, 26.0)],
        [action(date(2020, 5, 29), "dividend", 1.0), action(JUNE_1, "split", 4.0)],
    )

    assert (june_2.split_factor, june_2.value) == (1.0, pytest.approx(0.04))


def test_an_action_on_a_day_without_a_close_raises() -> None:
    with pytest.raises(ValueError, match="corporate action on 2020-06-02 but no close"):
        daily_total_returns(
            [bar(JUNE_1, 100.0), bar(JUNE_3, 50.0)], [action(JUNE_2, "split", 2.0)]
        )


@pytest.mark.parametrize(
    ("bars", "actions", "message"),
    [
        ([bar(JUNE_2, 1.0), bar(JUNE_1, 1.0)], [], "session order"),
        ([bar(JUNE_1, 1.0), bar(JUNE_1, 1.0)], [], "session order"),
        ([bar(JUNE_1, 1.0), bar(JUNE_2, 1.0, "other")], [], "mixed"),
        ([bar(JUNE_1, 1.0)], [action(JUNE_1, "split", 2.0, "other")], "among"),
        ([bar(JUNE_1, 1.0)], [action(JUNE_1, "merger", 1.0)], "unknown"),
        (
            [bar(JUNE_1, 1.0)],
            [action(JUNE_1, "split", 2.0), action(JUNE_1, "split", 3.0)],
            "two splits",
        ),
    ],
)
def test_inputs_must_be_one_securitys_in_order(
    bars: list[PriceBar], actions: list[CorporateAction], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        daily_total_returns(bars, actions)


def test_months_compound_their_daily_returns() -> None:
    # Up 1% every session from July 30 to September 1, 2020.
    sessions = calendar.sessions_between(date(2020, 7, 30), date(2020, 9, 1))
    bars = [bar(day, 100 * 1.01**i) for i, day in enumerate(sessions)]

    july, august, september = monthly_total_returns(daily_total_returns(bars, []))

    # July 31 is July's only return, and it starts from July 30, not June's last close.
    assert (july.month, july.start_session, july.end_session) == (
        date(2020, 7, 1),
        date(2020, 7, 30),
        date(2020, 7, 31),
    )
    assert not july.complete
    # August runs from July's last close to its own: 21 sessions.
    assert (august.start_session, august.end_session) == (
        date(2020, 7, 31),
        date(2020, 8, 31),
    )
    assert august.complete
    assert august.value == pytest.approx(1.01**21 - 1, rel=1e-12)
    assert august.available_at == utc(2020, 8, 31, 20)
    # September isn't over.
    assert (september.end_session, september.complete) == (date(2020, 9, 1), False)


def test_monthly_returns_need_daily_returns_in_order() -> None:
    june_2, june_3 = daily_total_returns(
        [bar(JUNE_1, 1.0), bar(JUNE_2, 1.0), bar(JUNE_3, 1.0)], []
    )
    with pytest.raises(ValueError, match="session order"):
        monthly_total_returns([june_3, june_2])


def test_returns_through_a_view(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-09-01") as view:
        dividend_day, after_the_gap, split_day = total_returns_as_of(
            view, "AAPL", start=date(2020, 8, 6)
        )

    # August 7: (395.18 + 0.82) / 400 - 1, the dividend reinvested at the close.
    assert dividend_day.session_date == date(2020, 8, 7)
    assert (dividend_day.dividend, dividend_day.value) == (0.82, pytest.approx(-0.01))
    # The fixture has no bars from August 10 to 27.
    assert after_the_gap.previous_session == date(2020, 8, 7)
    assert after_the_gap.value == pytest.approx(500 / 395.18 - 1)
    # August 31: 4 * 130 / 500 - 1, the 4-for-1 split.
    assert (split_day.split_factor, split_day.value) == (4.0, pytest.approx(0.04))


def test_a_return_is_known_at_its_close(fixture_store: Path) -> None:
    def returns(as_of: str) -> list[float]:
        with view_at(fixture_store, as_of) as view:
            daily = total_returns_as_of(view, "AAPL", start=date(2020, 8, 28))
        return [day.value for day in daily]

    assert returns("2020-08-31T15:59") == []  # the split day's bar isn't known yet
    assert returns("2020-08-31T16:00") == [pytest.approx(0.04)]


def test_the_canary_split_never_applies(fixture_store: Path) -> None:
    # The fixture's canary splits August 31 by 99, and becomes known only in 2099.
    with view_at(fixture_store, "2098-12-31") as view:
        (split_day,) = total_returns_as_of(
            view, "AAPL", date(2020, 8, 28), date(2020, 8, 31)
        )

    assert split_day.split_factor == 4.0


def test_price_levels_stay_raw_after_a_split(fixture_store: Path) -> None:
    # Returns account for the split; the bars a signal reads never do.
    with view_at(fixture_store, "2020-09-01") as view:
        bars = view.get_price_series_as_of("AAPL", date(2020, 8, 28))

    assert [b.close for b in bars] == [500.0, 130.0]


def test_returns_reads_are_in_the_access_log(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-09-01") as view:
        total_returns_as_of(view, "AAPL", start=date(2020, 8, 28))
        log = view.access_log

    assert [r.key for r in log if r.table == "price_bars"] == [
        ("apple", date(2020, 8, 28)),
        ("apple", date(2020, 8, 31)),
    ]
    assert [r for r in log if r.table == "corporate_actions"] == [
        AccessRecord(
            table="corporate_actions",
            key=("apple", date(2020, 8, 31), "split"),
            available_at=utc(2020, 8, 31, 20),
            source_ref="Apple's announced 4-for-1 split (not Tiingo's data)",
        )
    ]
