"""A run's metrics (S7.6; doc/reference/metrics.md), each on holding periods made by
hand: no store, and no prices.

tests/test_simulation.py checks them all at once, on a run of the loop that
doc/reference/metrics.md works by hand.
"""

import json
import math
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.backtest.metrics import equity_curve, summarize
from app.backtest.returns import PricePoint
from app.backtest.schedule import Rebalance, rebalances
from app.backtest.simulation import HoldingPeriod, Simulation
from app.backtest.spec import ExperimentSpec, parse_spec

CANONICAL = Path(__file__).parent / "fixtures" / "specs" / "canonical.json"


def two_years() -> ExperimentSpec:
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    data["period"] = {"start": "2021-01-01", "end": "2022-12-30"}
    return parse_spec(data)


SPEC = two_years()
SCHEDULE = rebalances(SPEC)
"""Monthly decisions from January 4, 2021, each filling at its day's close."""

JAN_4, FEB_1, MAR_1 = date(2021, 1, 4), date(2021, 2, 1), date(2021, 3, 1)

BENCHMARK_METRICS = (
    "hit_rate",
    "benchmark_total_return",
    "benchmark_cagr",
    "excess_return",
    "beta",
    "alpha",
    "mean_excess_return",
    "excess_t_stat",
)

ONE_PERCENT = [303 / 300 - 1, 306.03 / 303 - 1, 309.0903 / 306.03 - 1]
"""1% a month, as prices give it: the three differ in their last digits."""


def a_run(
    returns: Sequence[float],
    benchmark: Sequence[float | None] | None = None,
    *,
    rates: Sequence[float | None] | None = None,
    turnover: Sequence[float] | None = None,
) -> Simulation:
    """A run of monthly periods with these net returns, from January 4, 2021's close,
    each to the next month's fill.

    Without `benchmark`, no period has a benchmark return. Without `rates`, the
    risk-free rate is a published 0. Without `turnover`, the first fill buys the
    portfolio and the others trade nothing.
    """
    count = len(returns)
    benchmark = [None] * count if benchmark is None else benchmark
    rates = [0.0] * count if rates is None else rates
    turnover = [1.0, *[0.0] * (count - 1)] if turnover is None else turnover
    periods, value = [], 1.0
    for i, net in enumerate(returns):
        value *= 1 + net
        following = SCHEDULE[i + 1]
        periods.append(
            HoldingPeriod(
                rebalance=SCHEDULE[i],
                end=PricePoint(following.fill_session, following.fill_price),
                universe_size=0,
                holdings=(),
                trades=(),
                turnover=turnover[i],
                cost=0.0,
                gross_return=net,
                net_return=net,
                benchmark_return=benchmark[i],
                risk_free_rate=rates[i],
                value=value,
            )
        )
    return Simulation(SPEC, None, tuple(periods), ())


def test_cagr_annualizes_the_days_from_the_first_fill_to_the_end() -> None:
    # The portfolio doubles in twelve months, from January 4, 2021 to January 3, 2022:
    # 364 days, a little less than a year, so a little more than doubling a year.
    metrics = summarize(a_run([2 ** (1 / 12) - 1] * 12))

    assert (metrics.periods, metrics.start, metrics.end) == (
        12,
        PricePoint(JAN_4, "close"),
        PricePoint(date(2022, 1, 3), "close"),
    )
    assert metrics.years == pytest.approx(364 / 365.25)
    assert metrics.total_return == pytest.approx(1.0)
    assert metrics.cagr == pytest.approx(1.004766, abs=5e-7)
    assert (1 + metrics.cagr) ** metrics.years == pytest.approx(2.0)


def test_excess_return_is_the_difference_between_the_yearly_rates() -> None:
    # Over the same 364 days the benchmark gains half: 50.2090% a year, against
    # 100.4766%.
    doubling, half_again = 2 ** (1 / 12) - 1, 1.5 ** (1 / 12) - 1

    metrics = summarize(a_run([doubling] * 12, [half_again] * 12))

    assert metrics.benchmark_total_return == pytest.approx(0.5)
    assert metrics.benchmark_cagr == pytest.approx(0.502090, abs=5e-7)
    assert metrics.excess_return == pytest.approx(0.502676, abs=5e-7)


def test_a_run_that_starts_and_ends_in_one_session_has_no_cagr() -> None:
    # A next-day open fill on the period's last session: bought at its open, and
    # valued at its close.
    day = date(2021, 1, 5)
    rebalance = Rebalance(
        datetime(2021, 1, 4, 14, 30, tzinfo=UTC),
        datetime(2021, 1, 5, 14, 30, tzinfo=UTC),
        day,
        "open",
    )
    (period,) = a_run([0.01]).periods
    period = replace(period, rebalance=rebalance, end=PricePoint(day, "close"))

    metrics = summarize(Simulation(SPEC, None, (period,), ()))

    assert metrics.years == 0
    assert metrics.total_return == pytest.approx(0.01)
    assert metrics.cagr is None


def test_a_yearly_rate_too_big_for_a_number_is_left_out() -> None:
    # Ten times the money in a day would be 10 to the 365th in a year.
    (period,) = a_run([9.0], [9.0]).periods
    period = replace(period, end=PricePoint(date(2021, 1, 5), "close"))

    metrics = summarize(Simulation(SPEC, None, (period,), ()))

    assert metrics.total_return == pytest.approx(9.0)
    assert (metrics.cagr, metrics.benchmark_cagr, metrics.excess_return) == (
        None,
        None,
        None,
    )


def test_volatility_and_the_sharpe_ratio_annualize_monthly_returns() -> None:
    # A mean of 2% a month and a standard deviation of 1%, with bills at 1.2% a year,
    # which is 0.1% a month.
    metrics = summarize(a_run([0.03, 0.01, 0.02], rates=[1.2] * 3))

    assert metrics.volatility == pytest.approx(0.01 * math.sqrt(12))
    assert metrics.sharpe == pytest.approx((0.02 - 0.001) / 0.01 * math.sqrt(12))


def test_the_sharpe_ratio_uses_each_periods_own_rate() -> None:
    # 3%, 1%, and 2% over the bills' 1.2%, 2.4%, and 6% a year: 2.9%, 0.8%, and 1.5%,
    # whose mean is 26/15 of a percent and whose standard deviation isn't 1%.
    metrics = summarize(a_run([0.03, 0.01, 0.02], rates=[1.2, 2.4, 6.0]))

    over = [0.029, 0.008, 0.015]
    mean = sum(over) / 3
    spread = math.sqrt(sum((x - mean) ** 2 for x in over) / 2)
    assert metrics.sharpe == pytest.approx(mean / spread * math.sqrt(12))
    assert metrics.volatility == pytest.approx(0.01 * math.sqrt(12))  # of the returns


def test_a_missing_risk_free_rate_counts_as_zero() -> None:
    unknown = summarize(a_run([0.03, 0.01, 0.02], rates=[None] * 3))
    zero = summarize(a_run([0.03, 0.01, 0.02], rates=[0.0] * 3))

    assert unknown.sharpe == pytest.approx(2 * math.sqrt(12))
    assert unknown == zero


def test_max_drawdown_is_the_deepest_fall_from_a_peak() -> None:
    # 1.25, 1, 0.75, 1.125, and 1.0125: the fall from 1.25 to 0.75, not the one after.
    falls = summarize(a_run([0.25, -0.2, -0.25, 0.5, -0.1]))
    # The 1 it starts with is the first peak: 0.9, then 0.945.
    from_the_start = summarize(a_run([-0.1, 0.05]))

    assert falls.max_drawdown == pytest.approx(-0.4)
    assert from_the_start.max_drawdown == pytest.approx(-0.1)
    assert summarize(a_run([0.1, 0.2])).max_drawdown == 0


def test_turnover_leaves_out_the_first_fill() -> None:
    metrics = summarize(a_run([0.01] * 3, turnover=[1.0, 0.5, 0.25]))

    assert metrics.turnover == pytest.approx(0.375)


def test_the_hit_rate_is_the_share_of_periods_that_beat_the_benchmark() -> None:
    # Ahead, behind, ahead, and level, which isn't ahead.
    metrics = summarize(a_run([0.02, 0.01, 0.0, 0.03], [0.01, 0.02, -0.02, 0.03]))

    assert metrics.hit_rate == 0.5


def test_beta_and_alpha_regress_returns_over_the_risk_free_rate() -> None:
    # Over the bills' return, the portfolio makes twice what the benchmark does, and
    # 0.1% a month more. Without taking the bills' off, the slope isn't 2.
    benchmark = [0.01, -0.02, 0.03, 0.0]
    bills = [0.001, 0.002, 0.0005, 0.003]
    returns = [f + 2 * (b - f) + 0.001 for b, f in zip(benchmark, bills, strict=True)]

    metrics = summarize(a_run(returns, benchmark, rates=[1.2, 2.4, 0.6, 3.6]))

    assert metrics.beta == pytest.approx(2)
    assert metrics.alpha == pytest.approx(0.012)


def test_the_t_statistic_is_the_mean_excess_return_over_its_standard_error() -> None:
    # Ahead by 1%, 2%, and 3%: a mean of 2% and a standard deviation of 1%, over 3.
    metrics = summarize(a_run([0.02, 0.01, 0.05], [0.01, -0.01, 0.02]))

    assert metrics.mean_excess_return == pytest.approx(0.02)
    assert metrics.excess_t_stat == pytest.approx(0.02 / (0.01 / math.sqrt(3)))


def test_one_period_has_no_statistics() -> None:
    metrics = summarize(a_run([0.05], [0.02]))

    assert (metrics.volatility, metrics.sharpe, metrics.turnover) == (None, None, None)
    assert (metrics.beta, metrics.alpha, metrics.excess_t_stat) == (None, None, None)
    # It says what one period can.
    assert metrics.total_return == pytest.approx(0.05)
    assert metrics.benchmark_total_return == pytest.approx(0.02)
    assert (metrics.hit_rate, metrics.mean_excess_return) == (1.0, pytest.approx(0.03))


def test_returns_that_dont_vary_have_no_sharpe_ratio() -> None:
    assert len(set(ONE_PERCENT)) > 1  # so their standard deviation isn't quite 0

    metrics = summarize(a_run(ONE_PERCENT, [0.03, -0.01, 0.02]))

    assert metrics.volatility == 0
    assert metrics.sharpe is None
    assert metrics.beta == pytest.approx(0, abs=1e-12)  # they don't move with it
    assert metrics.alpha == pytest.approx(0.12)


def test_a_benchmark_that_never_varies_has_no_beta() -> None:
    metrics = summarize(a_run([0.03, -0.01, 0.02], ONE_PERCENT))

    assert (metrics.beta, metrics.alpha) == (None, None)
    # The rest of the comparison stands.
    assert metrics.hit_rate == pytest.approx(2 / 3)
    assert metrics.benchmark_total_return == pytest.approx(1.01**3 - 1)
    assert metrics.excess_t_stat is not None


def test_excess_returns_that_dont_vary_have_no_t_statistic() -> None:
    # Always 1% ahead.
    benchmark = [0.03, -0.01, 0.02]
    ahead = [b + one for b, one in zip(benchmark, ONE_PERCENT, strict=True)]

    metrics = summarize(a_run(ahead, benchmark))

    assert metrics.mean_excess_return == pytest.approx(0.01)
    assert metrics.excess_t_stat is None


def test_a_period_without_a_benchmark_return_leaves_no_benchmark_metrics() -> None:
    result = a_run([0.03, -0.01, 0.02], [0.01, None, 0.02])

    metrics = summarize(result)

    assert [getattr(metrics, name) for name in BENCHMARK_METRICS] == [None] * 8
    assert None not in (metrics.cagr, metrics.volatility, metrics.sharpe)
    # The curve has the benchmark up to the gap, and never after it.
    assert [point.benchmark for point in equity_curve(result)] == [
        1.0,
        pytest.approx(1.01),
        None,
        None,
    ]


def test_a_wiped_out_run_loses_everything() -> None:
    # A run that ends with nothing, in a period that returns -100%.
    metrics = summarize(a_run([0.1, -1.0], [0.01, 0.02]))

    assert (metrics.total_return, metrics.cagr, metrics.max_drawdown) == (-1, -1, -1)
    assert metrics.benchmark_cagr is not None
    assert metrics.excess_return == pytest.approx(-1 - metrics.benchmark_cagr)
    assert metrics.hit_rate == 0.5


def test_a_run_without_periods_has_no_metrics() -> None:
    empty = Simulation(SPEC, None, (), ())

    with pytest.raises(ValueError, match="without holding periods"):
        summarize(empty)
    assert equity_curve(empty) == ()


def test_the_equity_curve_starts_at_one_at_the_first_fill() -> None:
    curve = equity_curve(a_run([0.1, -0.5], [0.02, 0.0]))

    assert [(point.at, point.value, point.benchmark) for point in curve] == [
        (PricePoint(JAN_4, "close"), 1.0, 1.0),
        (PricePoint(FEB_1, "close"), pytest.approx(1.1), pytest.approx(1.02)),
        (PricePoint(MAR_1, "close"), pytest.approx(0.55), pytest.approx(1.02)),
    ]
