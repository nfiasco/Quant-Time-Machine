# /// script
# requires-python = ">=3.14"
# dependencies = ["pandas==3.0.6"]
#
# [tool.uv]
# exclude-newer = "2026-11-16T00:00:00Z"
# ///
"""S2.2: the canonical question in a notebook, with pandas and the raw downloads.

Run from backend/:  uv run spikes/tool_compare/notebook.py
Needs: an ingested raw cache in DATA_DIR (Tiingo prices and SEC company facts). No keys and no network.
Prints Markdown; saves nothing.

This is how a researcher without Quant Time Machine would answer the canonical question: download
Tiingo's daily prices and SEC's company facts, then write the strategy in pandas. It runs two versions:

- naive: the first thing most notebooks do. Each quarter's revenue counts from the day its quarter
  ended, the value is the latest one SEC has (restatements included), and today's member list is used
  for all 16 years.
- careful: each value counts from the day after its filing, a restatement only from its own filing,
  a derived fourth quarter only once both its filings are out, and each company only while it was a
  member.

Both use the canonical spec's other rules: a decision on each month's first trading day, filled at that
day's close, 12-1 momentum, revenue growth acceleration, equal weights, long only, and 10 bps of the
value traded. The functions are shared with backtrader_try.py, which runs the careful version in backtrader.
"""

import argparse
import json
import time
import tomllib
from itertools import pairwise
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[2]
SOURCES = BACKEND / "app" / "data" / "sources"
REVENUE = [  # the standard metric's concepts, most preferred first (metrics.toml), without its bank overrides
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
]
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "10-KT"}
FIRST, LAST = pd.Timestamp("2010-01-01"), pd.Timestamp("2025-12-31")
COST = 0.001  # 10 bps of the value traded


# --- Cell 1: find the downloads ---------------------------------------------------------------


def raw_index(data_dir: Path) -> dict[str, list[Path]]:
    """Map each cached URL, without its query, to the bodies fetched for it, oldest first.
    A ticker's prices can take several fetches: its full history, then shorter top-ups."""
    found: dict[str, list[tuple[str, Path]]] = {}
    for meta_path in (data_dir / "raw").glob("*/*/*.json"):
        meta = json.loads(meta_path.read_text())
        if meta["status_code"] == 200:
            found.setdefault(meta["url"].split("?")[0], []).append(
                (meta["fetched_at"], meta_path.with_suffix(".body"))
            )
    return {
        url: [path for _, path in sorted(fetches)] for url, fetches in found.items()
    }


def members() -> pd.DataFrame:
    """Universe v1's membership spells, with each member's Tiingo ticker and CIK."""
    securities = tomllib.loads((SOURCES / "securities.toml").read_text())["securities"]
    info = {}
    for security in securities:
        if "tiingo" in security.get("symbols", {}):  # every universe member has one
            cik = next(entry["cik"] for entry in security["history"] if "cik" in entry)
            info[security["id"]] = (security["symbols"]["tiingo"], cik)
    spells = tomllib.loads((SOURCES / "universes.toml").read_text())["universes"][0][
        "members"
    ]
    rows = []
    for spell in spells:
        ticker, cik = info[spell["security"]]
        removed = spell.get("removed")
        rows.append(
            {
                "id": spell["security"],
                "ticker": ticker,
                "cik": cik,
                "added": pd.Timestamp(spell["added"]),
                "removed": pd.Timestamp(removed) if removed else pd.Timestamp.max,
            }
        )
    return pd.DataFrame(rows)


# --- Cell 2: prices -----------------------------------------------------------------------------


def load_bars(index: dict[str, list[Path]], ticker: str) -> pd.DataFrame:
    """A ticker's Tiingo bars from every fetch; for a date fetched twice, the newer fetch wins."""
    paths = index[f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"]
    frame = pd.concat([pd.DataFrame(json.loads(path.read_text())) for path in paths])
    frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    return frame.drop_duplicates("date", keep="last").set_index("date").sort_index()


def load_prices(index: dict[str, list[Path]], tickers: list[str]) -> pd.DataFrame:
    """Tiingo's adjusted closes, one column per ticker. Ratios of adjusted closes are total returns.
    (Adjusted closes are rescaled after every later dividend and split, so a ratio is fine, a level isn't.)"""
    return pd.DataFrame(
        {ticker: load_bars(index, ticker)["adjClose"] for ticker in tickers}
    ).sort_index()


# --- Cell 3: revenue from SEC's company facts ----------------------------------------------------


def load_revenue(index: dict[str, list[Path]], cik: int) -> pd.DataFrame:
    """Every revenue value every 10-Q and 10-K reported, with the date it was filed."""
    facts = json.loads(
        index[f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"][
            -1
        ].read_text()
    )
    rows = []
    for rank, concept in enumerate(REVENUE):
        for fact in (
            facts["facts"]
            .get("us-gaap", {})
            .get(concept, {})
            .get("units", {})
            .get("USD", [])
        ):
            if fact.get("form") in FORMS and "start" in fact:
                rows.append(
                    {
                        "rank": rank,
                        "start": fact["start"],
                        "end": fact["end"],
                        "val": fact["val"],
                        "filed": fact["filed"],
                    }
                )
    frame = pd.DataFrame(rows, columns=["rank", "start", "end", "val", "filed"])
    for column in ("start", "end", "filed"):
        frame[column] = pd.to_datetime(frame[column])
    frame["days"] = (frame["end"] - frame["start"]).dt.days
    return frame


def quarters(facts: pd.DataFrame) -> pd.DataFrame:
    """One revenue per quarter: the latest filed value of the most preferred concept, plus fourth
    quarters derived as the year minus its first nine months. `known` is when the value was filed."""
    latest = (
        facts.sort_values("filed")
        .groupby(["rank", "start", "end"], as_index=False)
        .last()
    )
    three = latest[latest["days"].between(80, 100)]
    year = latest[latest["days"].between(350, 380)]
    nine = latest[latest["days"].between(260, 285)]
    derived = year.merge(nine, on=["rank", "start"], suffixes=("", "_9m"))
    derived = derived.assign(
        start=derived["end_9m"] + pd.Timedelta(days=1),
        val=derived["val"] - derived["val_9m"],
        filed=derived[["filed", "filed_9m"]].max(axis=1),
    )[["rank", "start", "end", "val", "filed"]]
    both = pd.concat([three[["rank", "start", "end", "val", "filed"]], derived])
    best = (
        both.sort_values("rank").groupby("end", as_index=False).first()
    )  # one concept per quarter
    return best.sort_values("end").reset_index(drop=True)


def acceleration(
    q: pd.DataFrame, decision: pd.Timestamp, recent_days: int | None = 200
) -> float | None:
    """This quarter's year-on-year revenue growth less last quarter's, from the quarters in q."""
    if q.empty or (recent_days and (decision - q["end"].iloc[-1]).days > recent_days):
        return None

    def find(end: pd.Timestamp, low: int, high: int) -> pd.Series | None:
        hits = q[(end - q["end"]).dt.days.between(low, high)]
        return hits.iloc[-1] if len(hits) else None

    def growth(row: pd.Series | None) -> float | None:
        earlier = find(row["end"], 350, 380) if row is not None else None
        if row is None or earlier is None or row["val"] <= 0 or earlier["val"] <= 0:
            return None
        return row["val"] / earlier["val"] - 1

    latest = q.iloc[-1]
    g_now, g_before = growth(latest), growth(find(latest["end"], 80, 119))
    return None if g_now is None or g_before is None else g_now - g_before


# --- Cell 4: decisions and signals -----------------------------------------------------------------


def decision_days(prices: pd.DataFrame) -> list[pd.Timestamp]:
    """The first trading day of each month, from SPY's sessions."""
    sessions = prices["SPY"].dropna().loc[FIRST:LAST].index
    return list(
        pd.Series(sessions, index=sessions).groupby(sessions.to_period("M")).first()
    )


def momentum(prices: pd.DataFrame, decision: pd.Timestamp) -> pd.Series:
    """12-1 momentum: from the last close before month M-12 to the last close before month M-1."""
    month = decision.to_period("M")
    start = prices.loc[: (month - 12).start_time - pd.Timedelta(days=1)].iloc[-1]
    end = prices.loc[: (month - 1).start_time - pd.Timedelta(days=1)].iloc[-1]
    return end / start - 1


VARIANTS = {  # name: (how revenue is dated, which companies count)
    "naive": ("period_end", "today"),
    "naive dating, members at the time": ("period_end", "members"),
    "careful dating, today's members": ("filed", "today"),
    "careful": ("filed", "members"),
}


def targets(
    variant: str,
    prices: pd.DataFrame,
    spells: pd.DataFrame,
    revenue: dict[str, pd.DataFrame],
) -> dict:
    """Each decision's holdings: companies with both signals above zero.

    Dating "period_end" takes SEC's data as it is today (restatements included) and counts each quarter
    from the day it ended; "filed" counts each value from the day after its filing. Universe "today" is
    every company on the list for all 16 years; "members" is each company only while it was a member."""
    dating, universe_rule = VARIANTS[variant]
    everything = {
        ticker: quarters(facts) for ticker, facts in revenue.items()
    }  # what SEC has today
    picks = {}
    for decision in decision_days(prices):
        if universe_rule == "today":
            universe = sorted(spells["ticker"].unique())
        else:
            current = spells[
                (spells["added"] <= decision) & (decision < spells["removed"])
            ]
            universe = sorted(current["ticker"].unique())
        mom = momentum(prices, decision)
        held = []
        for ticker in universe:
            if pd.isna(prices.at[decision, ticker]) or not mom.get(ticker, 0) > 0:
                continue
            if dating == "period_end":
                q = everything[ticker][everything[ticker]["end"] < decision]
                accel = acceleration(q, decision, recent_days=None)
            else:
                facts = revenue[ticker]
                accel = acceleration(
                    quarters(facts[facts["filed"] < decision]), decision
                )
            if accel is not None and accel > 0:
                held.append(ticker)
        picks[decision] = held
    return picks


def agreement(picks: dict, spells: pd.DataFrame, run_dir: Path) -> tuple[int, float]:
    """How many decisions hold exactly the engine's stocks, and the mean overlap (Jaccard)."""
    ticker_of = spells.drop_duplicates("id").set_index("id")["ticker"]
    engine: dict[pd.Timestamp, set[str]] = {}
    for holding in json.loads((run_dir / "holdings.json").read_text()):
        engine.setdefault(pd.Timestamp(holding["decision"]), set()).add(
            ticker_of[holding["security_id"]]
        )
    same, overlaps = 0, []
    for decision, held in picks.items():
        ours, theirs = set(held), engine.get(decision, set())
        same += ours == theirs
        overlaps.append(
            len(ours & theirs) / len(ours | theirs) if ours | theirs else 1.0
        )
    return same, sum(overlaps) / len(overlaps)


# --- Cell 5: the backtest -----------------------------------------------------------------------------


def backtest(prices: pd.DataFrame, picks: dict) -> pd.Series:
    """Hold each decision's picks at equal weights from its close to the next decision's close."""
    closes = (
        prices.ffill()
    )  # a company that stopped trading keeps its last close until it's sold
    days = list(picks) + [LAST]
    value, weights, curve = 1.0, pd.Series(dtype=float), {}
    for fill, next_fill in pairwise(days):
        target = (
            pd.Series(1 / len(picks[fill]), index=picks[fill])
            if picks[fill]
            else pd.Series(dtype=float)
        )
        turnover = target.sub(weights, fill_value=0).abs().sum()
        value *= 1 - COST * turnover
        curve[fill] = value
        growth = closes.loc[next_fill, target.index] / closes.loc[fill, target.index]
        period = (target * growth).sum() if len(target) else 1.0
        value *= period
        weights = target * growth / period if len(target) else target
    curve[LAST] = value
    return pd.Series(curve)


def cagr(curve: pd.Series) -> float:
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    return (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1


def load(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    index = raw_index(data_dir)
    spells = members()
    tickers = sorted(spells["ticker"].unique())
    prices = load_prices(index, [*tickers, "SPY"])
    ciks = spells.drop_duplicates("ticker").set_index("ticker")["cik"]
    revenue = {ticker: load_revenue(index, int(ciks[ticker])) for ticker in tickers}
    return prices, spells, revenue


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=BACKEND / "data")
    parser.add_argument(
        "--compare-run",
        type=Path,
        help="a saved run's directory, such as the canonical run's",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    prices, spells, revenue = load(args.data_dir)
    loaded = time.perf_counter() - started
    spy = prices["SPY"].loc[decision_days(prices)[0] : LAST]
    print("# The canonical question in a pandas notebook\n")
    print(
        f"Inputs: {len(revenue)} companies' company facts and {prices.shape[1]} price histories, loaded in {loaded:.1f} s.\n"
    )
    extra = " Same holdings as the run | Overlap, mean |" if args.compare_run else ""
    print(
        f"| Version | Growth of $1 | CAGR | Holdings, mean | Months with none | Took |{extra}"
    )
    print(
        "| --- | --- | --- | --- | --- | --- |"
        + (" --- | --- |" if args.compare_run else "")
    )
    for variant in VARIANTS:
        started = time.perf_counter()
        picks = targets(variant, prices, spells, revenue)
        curve = backtest(prices, picks)
        took = time.perf_counter() - started
        counts = [len(held) for held in picks.values()]
        row = (
            f"| {variant} | ${curve.iloc[-1]:.2f} | {cagr(curve):.1%} | {sum(counts) / len(counts):.1f} | "
            f"{counts.count(0)} of {len(counts)} | {took:.0f} s |"
        )
        if args.compare_run:
            same, overlap = agreement(picks, spells, args.compare_run)
            row += f" {same} of {len(picks)} | {overlap:.0%} |"
        print(row)
    print(
        f"| SPY, held | ${spy.iloc[-1] / spy.iloc[0]:.2f} | {cagr(spy / spy.iloc[0]):.1%} | | | |"
    )
    code = [
        line
        for line in Path(__file__).read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    print(
        f"\nThis script: {len(code)} non-blank, non-comment lines, docstrings included."
    )


if __name__ == "__main__":
    main()
