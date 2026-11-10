from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.backtest.returns import (
    HoldingReturn,
    PricePoint,
    daily_total_returns,
    fills_at,
    fills_at_as_of,
    holding_return,
    holding_return_as_of,
    monthly_total_returns,
    round_split_factor,
    total_returns_as_of,
)
from app.data import calendar
from app.data.records import CorporateAction, PriceBar
from app.data.store import write_rows
from app.data.tables import PRICE_BARS
from app.data.timeutil import parse_knowledge_time
from app.data.view import AccessRecord, PointInTimeView

# Every price here is made up, as in tests/fixtures/price_bars.csv: Tiingo's terms don't
# allow sharing its data. In the fixtures, Apple's August 2020 bars fall on its $0.82
# dividend (August 7) and its 4-for-1 split (August 31). How these returns compare
# with Tiingo's own adjusted closes is in tests/test_returns_vs_tiingo.py.


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def bar(
    day: date,
    close: float | None,
    security_id: str = "test",
    *,
    opened: float | None = None,
    volume: int | None = 1000,
) -> PriceBar:
    """A made-up bar, known at its session's close. It opens at `opened`, or at its
    close."""
    return PriceBar(
        security_id=security_id,
        ticker="TEST",
        cik=None,
        session_date=day,
        open=close if opened is None else opened,
        high=close,
        low=close,
        close=close,
        volume=volume,
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


def close(day: date) -> PricePoint:
    return PricePoint(day, "close")


def opening(day: date) -> PricePoint:
    return PricePoint(day, "open")


def test_a_holding_from_close_to_close_compounds_its_daily_returns() -> None:
    bars = [bar(JUNE_1, 100.0), bar(JUNE_2, 101.0), bar(JUNE_3, 103.02)]
    actions = [action(JUNE_2, "dividend", 1.0)]

    held = holding_return(bars, actions, close(JUNE_1), close(JUNE_3))

    # (101 + 1) / 100 * 103.02 / 101 - 1: the dividend reinvested on its ex-date.
    assert held == HoldingReturn(
        "test", close(JUNE_1), close(JUNE_3), pytest.approx(0.0404), True
    )
    growth = 1.0
    for day in daily_total_returns(bars, actions):
        growth *= 1 + day.value
    assert held is not None and held.value == pytest.approx(growth - 1, rel=1e-15)


def test_a_holding_bought_at_an_open_starts_from_it() -> None:
    bars = [bar(JUNE_1, 100.0, opened=95.0), bar(JUNE_2, 105.0)]
    # A dividend that day went to whoever held at the close before: not the buyer.
    actions = [action(JUNE_1, "dividend", 3.0)]

    held = holding_return(bars, actions, opening(JUNE_1), close(JUNE_2))

    assert held is not None
    assert held.value == pytest.approx(105 / 95 - 1)  # 100 / 95, then 105 / 100


@pytest.mark.parametrize(
    ("actions", "expected"),
    [
        ([], 98 / 100 - 1),
        # Sold at the ex-date's open, still with the dividend: (98 + 2) / 100 - 1.
        ([action(JUNE_2, "dividend", 2.0)], 0.0),
        # A 4-for-1 split that morning: 4 * 26 / 100 - 1, on the new shares' open.
        ([action(JUNE_2, "split", 4.0)], 0.04),
    ],
)
def test_a_holding_sold_at_an_open_keeps_that_days_actions(
    actions: list[CorporateAction], expected: float
) -> None:
    opened = 26.0 if actions and actions[0].action == "split" else 98.0
    bars = [bar(JUNE_1, 100.0), bar(JUNE_2, 99.0, opened=opened)]

    held = holding_return(bars, actions, close(JUNE_1), opening(JUNE_2))

    assert held == HoldingReturn(
        "test", close(JUNE_1), opening(JUNE_2), pytest.approx(expected), True
    )


def test_open_to_open_crosses_the_closes_between() -> None:
    bars = [
        bar(JUNE_1, 100.0, opened=99.0),
        bar(JUNE_2, 102.0),
        bar(JUNE_3, 104.0, opened=103.0),
    ]

    held = holding_return(bars, [], opening(JUNE_1), opening(JUNE_3))

    # 100 / 99, then 102 / 100, then the overnight 103 / 102: 103 / 99 in all.
    assert held is not None and held.value == pytest.approx(103 / 99 - 1)


@pytest.mark.parametrize("exit", [close(JUNE_3), opening(JUNE_3)])
def test_a_holding_whose_bars_end_is_valued_at_its_last_close(exit: PricePoint) -> None:
    # The security stopped trading after June 2.
    bars = [bar(JUNE_1, 100.0), bar(JUNE_2, 110.0)]

    held = holding_return(bars, [], close(JUNE_1), exit)

    assert held == HoldingReturn(
        "test", close(JUNE_1), close(JUNE_2), pytest.approx(0.1), complete=False
    )


def test_a_missing_open_values_the_holding_at_the_close_before() -> None:
    bars = [bar(JUNE_1, 100.0), bar(JUNE_2, 104.0), bar(JUNE_3, 120.0)]
    bars[-1] = replace(bars[-1], open=None)

    held = holding_return(bars, [], close(JUNE_1), opening(JUNE_3))

    assert held == HoldingReturn(
        "test", close(JUNE_1), close(JUNE_2), pytest.approx(0.04), complete=False
    )


@pytest.mark.parametrize(
    ("bars", "entry"),
    [
        ([bar(JUNE_2, 100.0)], close(JUNE_1)),  # no bar that day
        ([bar(JUNE_1, None), bar(JUNE_2, 100.0)], close(JUNE_1)),  # no close
        ([bar(JUNE_1, 0.0), bar(JUNE_2, 100.0)], close(JUNE_1)),
        # An open entry needs the open, and that day's close too.
        ([replace(bar(JUNE_1, 100.0), open=None), bar(JUNE_2, 100.0)], opening(JUNE_1)),
        ([bar(JUNE_1, None, opened=99.0), bar(JUNE_2, 100.0)], opening(JUNE_1)),
        # Nothing traded that day.
        ([bar(JUNE_1, 100.0, volume=0), bar(JUNE_2, 100.0)], close(JUNE_1)),
    ],
)
def test_a_holding_that_couldnt_be_bought_has_no_return(
    bars: list[PriceBar], entry: PricePoint
) -> None:
    assert holding_return(bars, [], entry, close(JUNE_3)) is None


def test_a_trade_fills_at_a_price_that_is_there() -> None:
    bars = [bar(JUNE_1, 100.0, opened=99.0), replace(bar(JUNE_2, 101.0), open=None)]

    assert fills_at(bars, opening(JUNE_1)) and fills_at(bars, close(JUNE_1))
    assert not fills_at(bars, opening(JUNE_2))  # no open that day
    assert fills_at(bars, close(JUNE_2))
    assert not fills_at(bars, close(JUNE_3))  # no bar


def test_a_holdings_exit_must_come_after_its_entry() -> None:
    bars = [bar(JUNE_1, 100.0, opened=98.0)]

    with pytest.raises(ValueError, match="exit, 2020-06-01 close, must come after"):
        holding_return(bars, [], close(JUNE_1), close(JUNE_1))
    with pytest.raises(ValueError, match="must come after its entry, 2020-06-01 close"):
        holding_return(bars, [], close(JUNE_1), opening(JUNE_1))
    # Bought at the open and valued at that day's close is a holding.
    held = holding_return(bars, [], opening(JUNE_1), close(JUNE_1))
    assert held is not None and held.value == pytest.approx(100 / 98 - 1)


def test_a_holding_return_through_a_view(fixture_store: Path) -> None:
    aug_6, aug_31 = date(2020, 8, 6), date(2020, 8, 31)
    with view_at(fixture_store, "2020-09-01") as view:
        by_ticker = holding_return_as_of(view, "AAPL", close(aug_6), close(aug_31))
        by_id = holding_return_as_of(
            view, view.get_security("apple"), close(aug_6), close(aug_31)
        )
        daily = total_returns_as_of(view, "AAPL", aug_6, aug_31)

    # The dividend of August 7, the gap to August 28, and the split of August 31.
    growth = 1.0
    for day in daily:
        growth *= 1 + day.value
    assert by_ticker == by_id
    assert by_ticker is not None
    assert (by_ticker.value, by_ticker.complete) == (pytest.approx(growth - 1), True)


def test_a_holding_return_needs_its_exits_bar_known(fixture_store: Path) -> None:
    # The view sees only bars whose sessions had closed, so a view before the exit's
    # close would mistake a bar not yet known for a missing one.
    aug_6, aug_31 = date(2020, 8, 6), date(2020, 8, 31)
    with (
        view_at(fixture_store, "2020-08-31T15:59") as view,
        pytest.raises(ValueError, match="2020-08-31 close is known only at"),
    ):
        holding_return_as_of(view, "AAPL", close(aug_6), close(aug_31))


def test_a_trade_fills_only_where_something_traded() -> None:
    # Tiingo repeats the last close in a bar for a session in which nothing traded.
    assert not fills_at([bar(JUNE_1, 100.0, volume=0)], close(JUNE_1))
    assert fills_at([bar(JUNE_1, 100.0, volume=None)], close(JUNE_1))  # unknown


@pytest.mark.parametrize("exit", [close(JUNE_3), opening(JUNE_3)])
def test_a_holding_is_valued_at_its_last_close_that_traded(exit: PricePoint) -> None:
    # The security stopped trading after June 2, and its vendor repeated June 2's close
    # on June 3, with no volume, as Tiingo did for Twitter on October 28, 2022.
    bars = [bar(JUNE_1, 100.0), bar(JUNE_2, 110.0), bar(JUNE_3, 110.0, volume=0)]

    held = holding_return(bars, [], close(JUNE_1), exit)

    assert held == HoldingReturn(
        "test", close(JUNE_1), close(JUNE_2), pytest.approx(0.1), complete=False
    )


def test_a_day_nothing_traded_between_trades_is_flat() -> None:
    # Trading halted on June 2, and resumed on June 3.
    bars = [bar(JUNE_1, 100.0), bar(JUNE_2, 100.0, volume=0), bar(JUNE_3, 105.0)]

    held = holding_return(bars, [], close(JUNE_1), close(JUNE_3))

    assert held == HoldingReturn(
        "test", close(JUNE_1), close(JUNE_3), pytest.approx(0.05), True
    )


def test_a_holding_ends_the_day_its_security_stopped_trading(
    fixture_store: Path,
) -> None:
    # Twitter's ticker ended on October 28, 2022, when it stopped trading. Made-up bars,
    # with a leftover on that day: Tiingo has 353 shares of Xilinx on the day Nasdaq
    # had halted it.
    oct_26, oct_27, oct_28 = date(2022, 10, 26), date(2022, 10, 27), date(2022, 10, 28)
    write_rows(
        fixture_store,
        PRICE_BARS,
        [
            {
                "security_id": "twitter",
                "session_date": day,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": volume,
                "source": "tiingo",
                "source_ref": f"made up: TWTR {day}",
                "available_at": calendar.session_close(day),
                "time_assumed": False,
            }
            for day, price, volume in (
                (oct_26, 52.0, 1000),
                (oct_27, 53.5, 1000),
                (oct_28, 54.2, 353),
            )
        ],
    )
    with view_at(fixture_store, "2022-11-01T16:00") as view:
        twitter = view.get_security("twitter")
        held = holding_return_as_of(
            view, twitter, close(oct_26), close(date(2022, 11, 1))
        )
        fills = fills_at_as_of(view, twitter, close(oct_28))
        leftover = view.get_price_series_as_of(twitter, oct_28, oct_28)

    assert held == HoldingReturn(
        "twitter",
        close(oct_26),
        close(oct_27),
        pytest.approx(53.5 / 52 - 1),
        complete=False,
    )
    # The leftover bar has volume, but no trade could fill there.
    assert fills_at(leftover, close(oct_28))
    assert not fills
