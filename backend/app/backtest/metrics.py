"""A run's performance metrics, against its benchmark (S7.6; doc/reference/metrics.md).

`summarize(simulation)` reduces a run's holding periods (app/backtest/simulation.py)
to the numbers a researcher judges it by, and `equity_curve(simulation)` gives the
portfolio's value beside the benchmark's at each period's end. Both only do arithmetic
on what the loop recorded: neither reads data, so the same run always gives the same
metrics.

Each holding period has three numbers, all for the same stretch of time:

- r, its `net_return`: the portfolio's return after costs.
- b, its `benchmark_return`: the benchmark's total return between the same prices.
- f, its risk-free return: the period's `risk_free_rate`, which is TB3MS in percent a
  year as last published by the decision, over 100 and over 12. A period without a rate
  counts 0, and the loop warns about it (`missing_risk_free`).

A period counts as a month, because decisions are monthly: volatility and the Sharpe
ratio annualize by the square root of 12, and alpha by 12. Only CAGR uses the calendar,
the days from the first fill to the last period's end.

A metric that can't be computed is None, never a number that looks like one:

- Fewer than two periods have no standard deviation, so no volatility, Sharpe ratio,
  beta, alpha, or t-statistic, and one period has no turnover after the first fill.
- Returns that don't vary can't be divided by their spread: a Sharpe ratio or a
  t-statistic needs returns that differ, and a beta needs a benchmark that moves.
- A period without a benchmark return leaves every benchmark metric empty: the run's
  benchmark can't be compounded over a gap.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from app.backtest.returns import PricePoint
from app.backtest.simulation import HoldingPeriod, Simulation

PERIODS_PER_YEAR = 12
"""Holding periods in a year: decisions are monthly."""

DAYS_PER_YEAR = 365.25

FLAT = 1e-12
"""Returns that differ by no more than this don't vary. Arithmetic on prices leaves
differences near 1e-16 between returns that are equal on paper, and dividing by their
spread would give a huge ratio that means nothing."""


@dataclass(frozen=True)
class EquityPoint:
    """The portfolio's value, and the benchmark's, at one point of a run."""

    at: PricePoint
    """The first fill, then each period's end."""
    value: float
    """The portfolio's value: 1 at the first fill, before it trades."""
    benchmark: float | None
    """What 1 in the benchmark at the first fill would be worth. None from the first
    period without a benchmark return on."""


@dataclass(frozen=True)
class Metrics:
    """A run's performance, after costs. Returns and rates are fractions: 0.05 is 5%."""

    periods: int
    """How many holding periods the run had."""
    start: PricePoint
    """The first fill, where the portfolio's value is 1."""
    end: PricePoint
    """The last period's end."""
    years: float
    """The days from `start`'s session to `end`'s, over 365.25."""
    total_return: float
    """The portfolio's final value, less the 1 it started with."""
    cagr: float | None
    """The yearly rate that compounds to the total return over `years`. None for a run
    that starts and ends in one session, or one so short that the rate overflows."""
    volatility: float | None
    """The standard deviation of the periods' net returns, annualized."""
    sharpe: float | None
    """The mean of the periods' returns over the risk-free rate, over their standard
    deviation, annualized."""
    max_drawdown: float
    """The portfolio's deepest fall from an earlier peak, as a return: -0.25 fell by a
    quarter, and 0 never fell. It's seen only at period ends."""
    turnover: float | None
    """The mean turnover of a rebalance after the first fill, which buys the whole
    portfolio from cash."""
    hit_rate: float | None
    """The share of periods whose net return beat the benchmark's."""
    benchmark_total_return: float | None
    """The benchmark's total return over the same periods."""
    benchmark_cagr: float | None
    """Its yearly rate, as for `cagr`."""
    excess_return: float | None
    """`cagr` less `benchmark_cagr`: how much more the portfolio grew a year."""
    beta: float | None
    """How much the portfolio's return over the risk-free rate moved with the
    benchmark's: the slope of one regressed on the other."""
    alpha: float | None
    """The same regression's intercept, annualized: the return over the risk-free rate
    that the benchmark's doesn't explain."""
    mean_excess_return: float | None
    """The mean of the periods' net returns less the benchmark's, a month."""
    excess_t_stat: float | None
    """That mean over its standard error: how many standard errors it is from zero."""


def summarize(simulation: Simulation) -> Metrics:
    """A run's metrics, from its holding periods (doc/reference/metrics.md has each
    formula, and a run worked by hand).

    Raises ValueError for a run without periods, which `simulate` never returns.
    """
    periods = simulation.periods
    if not periods:
        raise ValueError("a run without holding periods has no metrics")
    start, end = _first_fill(periods[0]), periods[-1].end
    years = (end.session - start.session).days / DAYS_PER_YEAR
    returns = [period.net_return for period in periods]
    risk_free = [_risk_free_return(period) for period in periods]
    over_risk_free = [r - f for r, f in zip(returns, risk_free, strict=True)]
    value = periods[-1].value
    cagr = _annualized(value, years)
    spread = _stdev(returns)

    benchmark = [period.benchmark_return for period in periods]
    compared = _compare(returns, over_risk_free, risk_free, benchmark, years)
    excess_return = None
    if cagr is not None and compared.cagr is not None:
        excess_return = cagr - compared.cagr
    return Metrics(
        periods=len(periods),
        start=start,
        end=end,
        years=years,
        total_return=value - 1,
        cagr=cagr,
        volatility=None if spread is None else spread * math.sqrt(PERIODS_PER_YEAR),
        sharpe=_scaled(over_risk_free, math.sqrt(PERIODS_PER_YEAR)),
        max_drawdown=_max_drawdown([period.value for period in periods]),
        turnover=(
            statistics.fmean(period.turnover for period in periods[1:])
            if len(periods) > 1
            else None
        ),
        hit_rate=compared.hit_rate,
        benchmark_total_return=compared.total_return,
        benchmark_cagr=compared.cagr,
        excess_return=excess_return,
        beta=compared.beta,
        alpha=compared.alpha,
        mean_excess_return=compared.mean_excess_return,
        excess_t_stat=compared.excess_t_stat,
    )


def equity_curve(simulation: Simulation) -> tuple[EquityPoint, ...]:
    """The portfolio's value and the benchmark's, both 1 at the first fill, then at
    each period's end. Empty for a run without periods."""
    periods = simulation.periods
    if not periods:
        return ()
    points = [EquityPoint(_first_fill(periods[0]), 1.0, 1.0)]
    benchmark: float | None = 1.0
    for period in periods:
        if benchmark is not None and period.benchmark_return is not None:
            benchmark *= 1 + period.benchmark_return
        else:
            benchmark = None  # and for every period after a gap
        points.append(EquityPoint(period.end, period.value, benchmark))
    return tuple(points)


@dataclass(frozen=True)
class _Compared:
    """The metrics that need the benchmark's return in every period."""

    total_return: float | None = None
    cagr: float | None = None
    hit_rate: float | None = None
    beta: float | None = None
    alpha: float | None = None
    mean_excess_return: float | None = None
    excess_t_stat: float | None = None


def _compare(
    returns: Sequence[float],
    over_risk_free: Sequence[float],
    risk_free: Sequence[float],
    benchmark: Sequence[float | None],
    years: float,
) -> _Compared:
    """The run against its benchmark, or nothing if a period has no benchmark return.
    `over_risk_free` is each of `returns` less the period's `risk_free`."""
    known = [b for b in benchmark if b is not None]
    if len(known) < len(benchmark):
        return _Compared()
    growth = math.prod(1 + b for b in known)
    excess = [r - b for r, b in zip(returns, known, strict=True)]
    beta, alpha = _regression(
        [b - f for b, f in zip(known, risk_free, strict=True)], over_risk_free
    )
    return _Compared(
        total_return=growth - 1,
        cagr=_annualized(growth, years),
        hit_rate=sum(r > b for r, b in zip(returns, known, strict=True)) / len(known),
        beta=beta,
        alpha=alpha,
        mean_excess_return=statistics.fmean(excess),
        excess_t_stat=_scaled(excess, math.sqrt(len(excess))),
    )


def _first_fill(period: HoldingPeriod) -> PricePoint:
    """Where a period starts: its decision's fill."""
    return PricePoint(period.rebalance.fill_session, period.rebalance.fill_price)


def _risk_free_return(period: HoldingPeriod) -> float:
    """What the risk-free rate the period's decision knew pays in a month. A period
    without one counts 0, as its warning says."""
    rate = period.risk_free_rate
    return 0.0 if rate is None else rate / 100 / PERIODS_PER_YEAR


def _annualized(growth: float, years: float) -> float | None:
    """The yearly rate at which 1 becomes `growth` in `years`: -1 if nothing is left.
    None for no time at all, or for so little that the rate overflows."""
    if years <= 0:
        return None
    if growth <= 0:
        return -1.0
    try:
        return growth ** (1 / years) - 1
    except OverflowError:
        return None


def _stdev(values: Sequence[float]) -> float | None:
    """The sample standard deviation: None for fewer than two values, and exactly 0
    for values that don't vary (FLAT)."""
    if len(values) < 2:
        return None
    if max(values) - min(values) <= FLAT:
        return 0.0
    return statistics.stdev(values)


def _scaled(values: Sequence[float], scale: float) -> float | None:
    """The values' mean over their standard deviation, times `scale`: a Sharpe ratio
    or a t-statistic. None if they have no standard deviation, or don't vary."""
    spread = _stdev(values)
    if not spread:
        return None
    return statistics.fmean(values) / spread * scale


def _regression(
    x: Sequence[float], y: Sequence[float]
) -> tuple[float | None, float | None]:
    """The slope of y on x, and the intercept a year. Neither if x doesn't vary."""
    if not _stdev(x):
        return None, None
    beta = statistics.covariance(x, y) / statistics.variance(x)
    alpha = statistics.fmean(y) - beta * statistics.fmean(x)
    return beta, alpha * PERIODS_PER_YEAR


def _max_drawdown(values: Sequence[float]) -> float:
    """The deepest fall of the portfolio's value from its highest so far, starting
    from the 1 it had at the first fill."""
    peak, deepest = 1.0, 0.0
    for value in values:
        peak = max(peak, value)
        deepest = min(deepest, value / peak - 1)
    return deepest
