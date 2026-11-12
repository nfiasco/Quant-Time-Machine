"""From a decision's signals to a target portfolio, and the trades that reach it (S7.3,
S7.5; doc/reference/portfolio.md).

A security can be held if it passes every filter. Without a ranking, each one that
passes gets the same weight. With one (S7.5), the securities that pass are ranked by a
signal, highest first, and only the ends of the ranking are held:

    size of each end = number ranked // quantiles, and at least 1

so the top quintile of 50 is 10 securities, and of 48, 9. Rounding down keeps the two
ends apart whenever two or more are ranked. Equal values rank in security ID order, so
a ranking never depends on the order its values came in.

- Long only: one end, top or bottom, at equal weights that add up to 1.
- Long-short: that end at weights that add up to 1, and the other end short, at
  weights that add up to -1.

Value weights wait for market caps (S6.6), and the engine rejects them until then.

Weights are fractions of the portfolio's value, and a short's is negative. Trading
from the weights before a fill to the target weights trades |target - before| of each
security, so the turnover is

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
from typing import Literal

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
    """Its ticker at the decision, or, for a position being closed, when it was
    opened."""
    fill: PricePoint
    """The price it traded at: the fill session's open or close."""
    weight_before: float
    """Its weight just before the fill: its last target, moved by its return since.
    Negative for a short."""
    weight_after: float
    """Its target weight, of the portfolio after costs: 0 for a position that's
    closed, and negative for a short."""
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


def ranked(values: Mapping[str, float]) -> list[str]:
    """Security IDs from the highest value to the lowest. Equal values go in security
    ID order."""
    return sorted(values, key=lambda security_id: (-values[security_id], security_id))


def quantile_size(count: int, quantiles: int) -> int:
    """How many of `count` ranked securities each end of a ranking holds: a share of
    1 / `quantiles`, rounded down, and at least one of any there are."""
    if quantiles < 2:
        raise ValueError(f"a ranking needs at least 2 quantiles, not {quantiles}")
    if count == 0:
        return 0
    return max(1, count // quantiles)


def ranked_weights(
    values: Mapping[str, float],
    *,
    quantiles: int,
    long: Literal["top", "bottom"],
    long_only: bool,
) -> dict[str, float]:
    """The target weights of a ranking's ends, by security ID, in ID order.

    `values` are the ranking signal's, for the securities that can be held. The `long`
    end, the top for the highest values, gets equal weights that add up to 1. Unless
    `long_only`, the other end is short, at equal weights that add up to -1. A
    long-short portfolio needs two securities, one for each end: with fewer, there are
    no weights.
    """
    order = ranked(values)
    size = quantile_size(len(order), quantiles)
    top, bottom = order[:size], order[len(order) - size :]
    held, shorted = (top, bottom) if long == "top" else (bottom, top)
    weights = equal_weights(held)
    if not long_only:
        if len(order) < 2:
            return {}
        weights |= {s: -weight for s, weight in equal_weights(shorted).items()}
    return dict(sorted(weights.items()))


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
