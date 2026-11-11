"""The signal library: what the simulation loop evaluates at each decision (S7.3, S7.4).

A spec names each of its signals' kind by its `type` (app/backtest/spec.py), and at
every decision the engine evaluates each signal for the universe's members, through the
view bound to the decision's time, so a signal can read only what was known then
(app/backtest/simulation.py). doc/reference/signals.md gives each signal's formula, the
data it reads, its minimum history, and the reasons it can have no value.

- `Signal` is what a kind of signal implements, and `SignalValue` its answer for one
  security: a value, or why there's none (base.py).
- `SIGNALS` lists the kinds the engine can evaluate, by `type`:
  - "momentum": a total return over whole months, 12-1 by default (momentum.py);
  - "revenue_growth" and "revenue_growth_acceleration": from the quarters filed by then
    (revenue.py);
  - "macro_change": a macro series' change over its latest releases (macro.py).

Values are fractions, as returns are: 0.01 is 1%. An absolute macro change is in its
series' units instead, such as percentage points for the unemployment rate.
"""

from collections.abc import Mapping
from types import MappingProxyType

from app.backtest.signals import macro, momentum, revenue
from app.backtest.signals.base import Signal, SignalValue

__all__ = ["SIGNALS", "Signal", "SignalValue"]

SIGNALS: Mapping[str, Signal] = MappingProxyType(
    {
        "momentum": momentum.momentum,
        "revenue_growth": revenue.revenue_growth,
        "revenue_growth_acceleration": revenue.revenue_growth_acceleration,
        "macro_change": macro.macro_change,
    }
)
"""The kinds of signal the engine can evaluate, by their `type` in a spec: one for each
signal in `SignalSpec` (app/backtest/spec.py)."""
