# /// script
# requires-python = ">=3.14"
# dependencies = ["backtrader==1.9.78.123", "pandas==3.0.6"]
#
# [tool.uv]
# exclude-newer = "2026-11-16T00:00:00Z"
# ///
"""S2.2: the canonical question in backtrader, an open-source Python backtester.

Run from backend/:  uv run spikes/tool_compare/backtrader_try.py
Needs: the same raw cache as notebook.py. No keys and no network. Prints Markdown; saves nothing.

backtrader simulates orders, cash, and commissions, but it has no fundamentals and no idea when a fact
became public. So the revenue signal still comes from the notebook's careful version (notebook.py),
and this script supplies what backtrader adds: one price feed per company, a strategy that rebalances
on each decision day, fills at that day's close, and 10 bps commissions.
"""

import argparse
import time
from pathlib import Path

import backtrader as bt
import notebook as nb  # the careful version's data loading and signals
import pandas as pd

START_CASH = 10_000_000.0  # large, so whole-share rounding barely matters
CASH_BUFFER = 0.995  # invest this share of the portfolio: without it, buys after commissions are rejected for "Margin"


class Canonical(bt.Strategy):
    params = (("picks", None),)

    def __init__(self) -> None:
        self.by_name = {data._name: data for data in self.datas}
        self.values: dict[pd.Timestamp, float] = {}
        self.rejected = 0

    def notify_order(self, order: bt.Order) -> None:
        self.rejected += order.status in (order.Margin, order.Rejected)

    def prenext(self) -> None:
        # backtrader waits until every feed has a bar. Companies listed after 2010 (AbbVie, PayPal,
        # Airbnb, ...) would hold the whole strategy back until 2020, so trade anyway.
        self.next()

    def next(self) -> None:
        today = pd.Timestamp(self.datetime.date(0))
        self.values[today] = self.broker.getvalue()
        if today not in self.p.picks:
            return
        held = set(self.p.picks[today])
        value = self.broker.getvalue()
        target = {
            name: (CASH_BUFFER / len(held) if name in held else 0.0)
            for name in self.by_name
        }
        change = {
            name: target[name] * value - self.getposition(data).size * data.close[0]
            for name, data in self.by_name.items()
            if len(data) and (target[name] or self.getposition(data).size)
        }
        # Orders fill in the order they're placed, and a buy that comes before a sell is rejected for
        # "Margin" when the cash isn't there yet. So place every sale, then every purchase.
        for name in sorted(change, key=change.get):
            self.order_target_percent(self.by_name[name], target[name])


def run(data_dir: Path) -> tuple[pd.Series, dict, float, int]:
    prices, spells, revenue = nb.load(data_dir)
    picks = nb.targets("careful", prices, spells, revenue)
    index = nb.raw_index(data_dir)
    sessions = prices["SPY"].dropna().loc[nb.FIRST : nb.LAST].index
    started = time.perf_counter()
    cerebro = bt.Cerebro(stdstats=False)
    for ticker in sorted(spells["ticker"].unique()):
        bars = nb.load_bars(index, ticker).loc[nb.FIRST : nb.LAST]
        if bars.empty:
            continue
        # A feed that ends can never fill an order, so an acquired company would be held forever.
        # Repeat its last close until the end, at zero volume, so the next decision can sell it.
        bars = bars.reindex(sessions[sessions >= bars.index[0]]).ffill()
        frame = pd.DataFrame(
            {  # adjusted bars, so a price change includes dividends and splits
                "open": bars["adjOpen"],
                "high": bars["adjHigh"],
                "low": bars["adjLow"],
                "close": bars["adjClose"],
                "volume": bars["adjVolume"],
            }
        )
        cerebro.adddata(bt.feeds.PandasData(dataname=frame), name=ticker)
    cerebro.broker.setcash(START_CASH)
    cerebro.broker.setcommission(commission=nb.COST)  # a fraction of the value traded
    cerebro.broker.set_coc(
        True
    )  # "cheat on close": fill at the close of the bar the order was placed on
    cerebro.broker.set_checksubmit(
        False
    )  # otherwise buys are checked against cash before the sells fill
    cerebro.addstrategy(Canonical, picks=picks)
    strategy = cerebro.run()[0]
    took = time.perf_counter() - started
    return pd.Series(strategy.values), picks, took, strategy.rejected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=nb.BACKEND / "data")
    args = parser.parse_args()
    values, picks, took, rejected = run(args.data_dir)
    curve = values.loc[next(iter(picks)) :] / START_CASH
    print("# The canonical question in backtrader\n")
    print("| Version | Growth of $1 | CAGR | Orders rejected | Took |")
    print("| --- | --- | --- | --- | --- |")
    print(
        f"| careful signals, backtrader fills | ${curve.iloc[-1]:.2f} | {nb.cagr(curve):.1%} | {rejected} | {took:.0f} s |"
    )
    code = [
        line
        for line in Path(__file__).read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    print(
        f"\nThis script: {len(code)} non-blank, non-comment lines, docstrings included, plus notebook.py's signals."
    )


if __name__ == "__main__":
    main()
