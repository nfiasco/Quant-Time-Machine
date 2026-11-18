"""The backtest engine: deterministic, reproducible strategy simulations.

It reads data only through the point-in-time data layer (`app.data`), never the store
itself. So far it has:

- `returns`: daily and monthly total returns from raw prices, splits, and dividends
  (S6.4), and holding returns from one fill's price to the next (S7.3)
- `spec`: the experiment spec, a validated document that describes a backtest, with
  its JSON Schema (S7.1) and the signal types the catalog lists (S8.5)
- `schedule`: decision times and their fills, which always come strictly after them
  (S7.2)
- `signals`: what the loop asks of a signal (S7.3), and the signal library it
  evaluates: momentum, revenue growth and its acceleration, and a macro series' change
  (S7.4; doc/reference/signals.md)
- `portfolio`: equal-weight targets from the filters, and the trades and costs that
  reach them (S7.3); a ranking's top or bottom quantile, long only or long-short
  (S7.5; doc/reference/portfolio.md)
- `simulation`: the loop, which steps through a spec's decisions, each reading only
  what was known then through a view factory (S7.3)
- `metrics`: a run's CAGR, volatility, Sharpe ratio, drawdown, and turnover, and its
  excess return, hit rate, beta, alpha, and t-statistic against the benchmark, with
  the risk-free rate each decision knew (S7.6; doc/reference/metrics.md)
- `coverage`: what data a run's decisions lacked, by security and year, and the
  holdings it valued at their last close (S6.7; doc/reference/runs.md)
- `canonical`: canonical JSON, so equal values give equal bytes and hashes (S7.7)
- `audit`: what each view a run opened read, summarized from its access log, with
  each row's `available_at` (S7.7)
- `records`: a run's record, the files that say what it used and produced, keyed by
  a run ID that hashes its spec, data version, and engine version (S7.7;
  doc/reference/runs.md)

Running a spec against the store and saving its record is app/runs.py's job: the
engine itself never learns where the store is.
"""

ENGINE_VERSION = "1.1.0"
"""The version of the code that turns a spec and a data version into results. It's
part of every run ID (app/backtest/records.py), so two runs with the same ID must have
the same results.

Raise it with any change that can change a saved result: to a signal, the portfolio,
returns, metrics, or the loop here, or to how app/data reads the store, such as how a
quarter is derived. `test_a_pinned_runs_files_never_change` in tests/test_records.py
fails until you do.
"""
