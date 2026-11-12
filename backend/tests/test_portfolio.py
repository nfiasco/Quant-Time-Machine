"""Filters, rankings, weights, and the trades between them (S7.3, S7.5), on made-up
weights and values: doc/reference/portfolio.md has the formulas."""

from datetime import date

import pytest

from app.backtest.portfolio import (
    Trade,
    equal_weights,
    passes,
    quantile_size,
    ranked,
    ranked_weights,
    trade_to_target,
)
from app.backtest.returns import PricePoint
from app.backtest.spec import FilterSpec

FILL = PricePoint(date(2021, 2, 1), "close")
TICKERS = {"alpha": "AAA", "beta": "BBB", "gamma": "CCC"}

SIX = {"alpha": 0.5, "beta": 0.4, "gamma": 0.3, "delta": 0.2, "eta": 0.1, "zeta": 0.0}
"""Six securities' values for a ranking's signal, from the highest to the lowest."""


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


def test_a_ranking_runs_from_the_highest_value_to_the_lowest() -> None:
    values = {"alpha": 0.1, "beta": 0.3, "gamma": -0.2, "delta": 0.2}

    assert ranked(values) == ["beta", "delta", "alpha", "gamma"]
    assert ranked({}) == []


def test_equal_values_rank_in_security_id_order() -> None:
    # Whatever order they arrive in, so a ranking is the same on every run.
    values = {"gamma": 0.1, "alpha": 0.1, "beta": 0.5, "delta": 0.1}

    assert ranked(values) == ["beta", "alpha", "delta", "gamma"]
    assert ranked(dict(reversed(values.items()))) == ranked(values)


@pytest.mark.parametrize(
    ("count", "quantiles", "size"),
    [
        (50, 5, 10),  # a quintile of the starter universe
        (48, 5, 9),  # rounded down from 9.6
        (50, 10, 5),
        (10, 5, 2),
        (9, 5, 1),
        (7, 3, 2),
        (4, 2, 2),
        (3, 2, 1),  # the middle one is in neither half
        (5, 5, 1),
        (4, 5, 1),  # fewer than the quantiles: one, not none
        (1, 5, 1),
        (2, 100, 1),
        (0, 5, 0),
    ],
)
def test_each_end_of_a_ranking_holds_a_quantile_rounded_down(
    count: int, quantiles: int, size: int
) -> None:
    assert quantile_size(count, quantiles) == size


def test_a_ranking_needs_two_quantiles() -> None:
    with pytest.raises(ValueError, match="at least 2 quantiles"):
        quantile_size(10, 1)


def test_a_long_only_ranking_holds_one_end() -> None:
    # A third of six is two.
    top = ranked_weights(SIX, quantiles=3, long="top", long_only=True)
    bottom = ranked_weights(SIX, quantiles=3, long="bottom", long_only=True)

    assert top == {"alpha": 0.5, "beta": 0.5}
    assert bottom == {"eta": 0.5, "zeta": 0.5}


def test_a_long_short_ranking_is_long_one_end_and_short_the_other() -> None:
    top = ranked_weights(SIX, quantiles=3, long="top", long_only=False)
    bottom = ranked_weights(SIX, quantiles=3, long="bottom", long_only=False)

    assert top == {"alpha": 0.5, "beta": 0.5, "eta": -0.5, "zeta": -0.5}
    assert bottom == {"alpha": -0.5, "beta": -0.5, "eta": 0.5, "zeta": 0.5}
    assert list(top) == sorted(top)  # in security ID order, not the ranking's


@pytest.mark.parametrize("quantiles", [2, 3, 5, 10])
@pytest.mark.parametrize("count", range(2, 13))
def test_the_ends_of_a_long_short_ranking_never_overlap(
    count: int, quantiles: int
) -> None:
    values = {f"s{number:02}": float(number) for number in range(count)}

    weights = ranked_weights(values, quantiles=quantiles, long="top", long_only=False)

    long = [weight for weight in weights.values() if weight > 0]
    short = [weight for weight in weights.values() if weight < 0]
    # A security in both ends would be counted once here, and the lengths would differ.
    assert len(long) == len(short) == quantile_size(count, quantiles)
    assert sum(long) == pytest.approx(1)
    assert sum(short) == pytest.approx(-1)


def test_a_tie_at_the_cutoff_goes_to_the_lower_security_id() -> None:
    # All four tie, so the ranking is their ID order: alpha, beta, delta, gamma.
    values = dict.fromkeys(["gamma", "alpha", "delta", "beta"], 0.2)

    weights = ranked_weights(values, quantiles=2, long="top", long_only=False)

    assert weights == {"alpha": 0.5, "beta": 0.5, "delta": -0.5, "gamma": -0.5}


def test_one_security_cant_be_long_and_short() -> None:
    alone = {"alpha": 0.3}

    assert ranked_weights(alone, quantiles=5, long="top", long_only=False) == {}
    assert ranked_weights(alone, quantiles=5, long="top", long_only=True) == {
        "alpha": 1.0
    }
    assert ranked_weights({}, quantiles=5, long="top", long_only=True) == {}


def test_opening_a_long_short_portfolio_trades_twice_its_value() -> None:
    trades, turnover, cost = trade_to_target(
        {}, {"alpha": 1.0, "beta": -1.0}, bps_per_trade=10, fill=FILL, tickers=TICKERS
    )

    assert trades == (
        Trade("alpha", "AAA", FILL, 0.0, 1.0, pytest.approx(0.001)),
        Trade("beta", "BBB", FILL, 0.0, -1.0, pytest.approx(0.001)),
    )
    # All of it bought, and as much again sold short: 10 bps of both.
    assert (turnover, cost) == (2.0, pytest.approx(0.002))


def test_swapping_a_long_and_a_short_trades_four_times_the_portfolio() -> None:
    # Each is closed, 1, and opened the other way, 1 more.
    trades, turnover, cost = trade_to_target(
        {"alpha": 1.0, "beta": -1.0},
        {"alpha": -1.0, "beta": 1.0},
        bps_per_trade=10,
        fill=FILL,
        tickers=TICKERS,
    )

    assert [t.traded for t in trades] == [2.0, 2.0]
    assert (turnover, cost) == (4.0, pytest.approx(0.004))


def test_a_short_that_rose_is_bought_back_to_its_target() -> None:
    # Beta, short, rose 10% while alpha was flat, so the portfolio is worth 0.9: alpha
    # is 1 / 0.9 of it, and beta -1.1 / 0.9.
    before = {"alpha": 1 / 0.9, "beta": -1.1 / 0.9}

    trades, turnover, _ = trade_to_target(
        before,
        {"alpha": 1.0, "beta": -1.0},
        bps_per_trade=10,
        fill=FILL,
        tickers=TICKERS,
    )

    assert [(t.security_id, t.weight_after) for t in trades] == [
        ("alpha", 1.0),  # some sold
        ("beta", -1.0),  # some bought back
    ]
    assert [t.traded for t in trades] == [
        pytest.approx(1 / 9),
        pytest.approx(2 / 9),
    ]
    assert turnover == pytest.approx(1 / 3)
