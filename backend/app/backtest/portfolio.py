"""From a decision's signals to a target portfolio, and the trades that reach it (S7.3).

Version 1 builds what experiment spec v1 can ask for with equal weights and long-only
positions: a security is held if it passes every filter, and each one held gets the
same weight. Ranking, value weights, and long-short portfolios are S7.5's.

Weights are fractions of the portfolio's value. Trading from the weights before a fill
to the target weights trades |target - before| of each security, so the turnover is

    turnover = sum over securities of |target - before|

and the trades cost `bps_per_trade` basis points of the value traded (app/backtest/
spec.py): cost = bps / 10,000 * turnover, as a fraction of the portfolio's value before
trading. The cost comes out of the portfolio, so after trading the weights are the
targets, of a portfolio worth (1 - cost) times as much. Charging the value traded
before the cost is the usual convention: the exact trades, on the smaller portfolio,
differ by about the cost times itself.
"""

import operator
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from app.backtest.returns import PricePoint
from app.backtest.spec import FilterSpec

BASIS_POINT = 1e-4
"""One basis point, 0.01%."""

_OPERATORS: Mapping[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


@dataclass(frozen=True)
class Trade:
    """One security's trade at a fill."""

    security_id: str
    ticker: str | None
    """Its ticker at the decision, or, for a sale, when it was bought."""
    fill: PricePoint
    """The price it traded at: the fill session's open or close."""
    weight_before: float
    """Its weight just before the fill: its last target, moved by its return since."""
    weight_after: float
    """Its target weight, of the portfolio after costs: 0 for a sale of all of it."""
    cost: float
    """What the trade cost, as a fraction of the portfolio's value before trading."""

    @property
    def traded(self) -> float:
        """The value traded, as a fraction of the portfolio's value before trading."""
        return abs(self.weight_after - self.weight_before)


def passes(condition: FilterSpec, value: float) -> bool:
    """Whether a signal's value meets a filter, such as rev_accel > 0."""
    return _OPERATORS[condition.op](value, condition.value)


def equal_weights(security_ids: Sequence[str]) -> dict[str, float]:
    """The same weight for each security, adding up to 1; none for no securities."""
    if not security_ids:
        return {}
    weight = 1 / len(security_ids)
    return {security_id: weight for security_id in security_ids}


def trade_to_target(
    before: Mapping[str, float],
    target: Mapping[str, float],
    *,
    bps_per_trade: float,
    fill: PricePoint,
    tickers: Mapping[str, str | None],
) -> tuple[tuple[Trade, ...], float, float]:
    """The trades that take a portfolio from its weights `before` to `target` at a
    fill, with their turnover and cost.

    Trades come in security ID order, and a security whose weight doesn't change isn't
    traded. `tickers` gives each traded security's ticker. Returns the trades, the
    turnover, and the cost, as the module's docstring defines them.
    """
    if bps_per_trade < 0:
        raise ValueError(f"a cost must be at least 0 bps, not {bps_per_trade}")
    rate = bps_per_trade * BASIS_POINT
    trades = []
    for security_id in sorted(before.keys() | target.keys()):
        weight_before = before.get(security_id, 0.0)
        weight_after = target.get(security_id, 0.0)
        if weight_after == weight_before:
            continue
        trades.append(
            Trade(
                security_id=security_id,
                ticker=tickers[security_id],
                fill=fill,
                weight_before=weight_before,
                weight_after=weight_after,
                cost=rate * abs(weight_after - weight_before),
            )
        )
    turnover = sum(trade.traded for trade in trades)
    return tuple(trades), turnover, rate * turnover
