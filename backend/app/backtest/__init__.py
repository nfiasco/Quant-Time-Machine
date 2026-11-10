"""The backtest engine: deterministic, reproducible strategy simulations.

It reads data only through the point-in-time data layer (`app.data`), never the store
itself. So far it has:

- `returns`: daily and monthly total returns from raw prices, splits, and dividends
  (S6.4), and holding returns from one fill's price to the next (S7.3)
- `spec`: the experiment spec, a validated document that describes a backtest, with
  its JSON Schema (S7.1) and the signal types the catalog lists (S8.5)
- `schedule`: decision times and their fills, which always come strictly after them
  (S7.2)
- `signals`: what the loop asks of a signal, and the signals it can evaluate (S7.3)
- `portfolio`: equal-weight targets from the filters, and the trades and costs that
  reach them (S7.3)
- `simulation`: the loop, which steps through a spec's decisions, each reading only
  what was known then through a view factory (S7.3)
"""
