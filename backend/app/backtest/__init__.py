"""The backtest engine: deterministic, reproducible strategy simulations.

It reads data only through the point-in-time data layer (`app.data`), never the store
itself. So far it has:

- `returns`: daily and monthly total returns from raw prices, splits, and dividends
  (S6.4)
"""
