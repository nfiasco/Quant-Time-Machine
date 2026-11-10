from datetime import date

import pytest

from app.backtest.portfolio import Trade, equal_weights, passes, trade_to_target
from app.backtest.returns import PricePoint
from app.backtest.spec import FilterSpec

FILL = PricePoint(date(2021, 2, 1), "close")
TICKERS = {"alpha": "AAA", "beta": "BBB", "gamma": "CCC"}


@pytest.mark.parametrize(
    ("op", "value", "expected"),
    [
        (">", 0.0, False),
        (">=", 0.0, True),
        ("<", 0.0, False),
        ("<=", 0.0, True),
        (">", 0.5, True),
        ("<", -0.5, True),
        ("<=", 0.5, False),
    ],
)
def test_a_filter_compares_a_signals_value_with_its_own(
    op: str, value: float, expected: bool
) -> None:
    condition = FilterSpec.model_validate({"signal": "mom", "op": op, "value": 0})

    assert passes(condition, value) is expected


def test_equal_weights_add_up_to_one() -> None:
    assert equal_weights(["alpha", "beta", "gamma", "delta"]) == {
        "alpha": 0.25,
        "beta": 0.25,
        "gamma": 0.25,
        "delta": 0.25,
    }
    assert equal_weights([]) == {}


def test_buying_from_cash_trades_the_whole_portfolio() -> None:
    trades, turnover, cost = trade_to_target(
        {},
        equal_weights(["alpha", "beta"]),
        bps_per_trade=10,
        fill=FILL,
        tickers=TICKERS,
    )

    assert trades == (
        Trade("alpha", "AAA", FILL, 0.0, 0.5, pytest.approx(0.0005)),
        Trade("beta", "BBB", FILL, 0.0, 0.5, pytest.approx(0.0005)),
    )
    # 10 bps of everything bought: 0.1% of the portfolio.
    assert (turnover, cost) == (1.0, pytest.approx(0.001))


def test_rebalancing_trades_the_difference() -> None:
    # Alpha rose 10% and beta fell 10% since they were bought at half each. Now the
    # target is alpha and gamma.
    before = {"alpha": 0.55, "beta": 0.45}

    trades, turnover, cost = trade_to_target(
        before,
        {"alpha": 0.5, "gamma": 0.5},
        bps_per_trade=10,
        fill=FILL,
        tickers=TICKERS,
    )

    assert [(t.security_id, t.weight_before, t.weight_after) for t in trades] == [
        ("alpha", 0.55, 0.5),  # trimmed back to its target
        ("beta", 0.45, 0.0),  # sold
        ("gamma", 0.0, 0.5),  # bought
    ]
    assert [t.traded for t in trades] == [pytest.approx(0.05), 0.45, 0.5]
    assert turnover == pytest.approx(1.0)
    assert cost == pytest.approx(0.001)
    assert sum(t.cost for t in trades) == pytest.approx(cost)


def test_a_weight_that_doesnt_change_isnt_traded() -> None:
    trades, turnover, cost = trade_to_target(
        {"alpha": 0.5}, {"alpha": 0.5}, bps_per_trade=10, fill=FILL, tickers=TICKERS
    )

    assert (trades, turnover, cost) == ((), 0, 0)


def test_costs_cant_be_negative() -> None:
    with pytest.raises(ValueError, match="at least 0 bps"):
        trade_to_target({}, {}, bps_per_trade=-1, fill=FILL, tickers=TICKERS)
