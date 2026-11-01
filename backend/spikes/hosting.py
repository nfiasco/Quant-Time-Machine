"""Spike S1.6: how big is the point-in-time store, and how would a backtest run on a host?

Unlike the other spikes, this one uses the app's own read path (PointInTimeView), so it
runs in the project's environment rather than with its own pinned dependencies. Run it
from backend/, after ingesting:

    uv run python -m spikes.hosting [--data-dir DIR] [--tickers 100]

On a host, run it the same way inside the deployed image. It prints a Markdown report:

1. The store's size: rows, Parquet files, and bytes per table, and the raw cache's bytes
   per source.
2. The installed packages' size, to compare with a serverless bundle limit.
3. A backtest-shaped workload. For each month's first trading day at 09:30 ET, it opens
   one PointInTimeView and reads, for each of N tickers, a 252-session price history and
   the latest 10-Q, plus UNRATE once, as the canonical example's signals would. The six
   M2 tickers take turns standing in for a universe of N, each under the ticker it had
   on that day (FB became META in 2022; TWTR stopped trading in 2022). It reports the
   calendar's warm-up, the time spent opening views and reading, and peak memory.

Cycling six tickers measures per-query overhead faithfully, but not the data volume of a
real 100-security universe, so treat the read times as a lower bound.
"""

import argparse
import resource
import sys
import sysconfig
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from app.config import get_settings
from app.data import calendar
from app.data.sources.securities import CURATED
from app.data.store import connect, store_dir, table_files, table_source
from app.data.tables import TABLES
from app.data.view import PointInTimeView


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, help="default: DATA_DIR")
    parser.add_argument("--tickers", type=int, default=100, help="universe size")
    parser.add_argument("--start", type=int, default=2010, help="first year")
    parser.add_argument("--end", type=int, default=2025, help="last year")
    parser.add_argument("--lookback", type=int, default=252, help="sessions read")
    args = parser.parse_args()
    data_dir = args.data_dir or get_settings().data_dir

    print("# Hosting spike (S1.6)\n")
    print(f"Python {sys.version.split()[0]} on {sys.platform}; data in {data_dir}\n")
    report_store(store_dir(data_dir))
    report_raw_cache(data_dir / "raw")
    report_packages()
    report_workload(store_dir(data_dir), args)


def report_store(store: Path) -> None:
    print("## The point-in-time store\n")
    print("| Table | Rows | Files | Bytes |")
    print("| --- | ---: | ---: | ---: |")
    connection = connect()
    total_rows = total_files = total_bytes = 0
    for name, spec in TABLES.items():
        files = table_files(store, spec)
        size = sum(f.stat().st_size for f in files)
        query = f"SELECT count(*) FROM {table_source(store, spec)}"
        rows = connection.execute(query).fetchone()[0]
        print(f"| `{name}` | {rows:,} | {len(files)} | {size:,} |")
        total_rows, total_files = total_rows + rows, total_files + len(files)
        total_bytes += size
    total = f"**{total_rows:,}** | **{total_files}** | **{total_bytes:,}**"
    print(f"| **Total** | {total} |")
    print(f"\nAbout {total_bytes / total_rows:.1f} bytes per row.\n")


def report_raw_cache(raw: Path) -> None:
    print("## The raw cache (not deployed)\n")
    print("| Source | Responses | Bytes |")
    print("| --- | ---: | ---: |")
    sources = sorted(p for p in raw.iterdir() if p.is_dir()) if raw.is_dir() else []
    for source in sources:
        bodies = list(source.rglob("*.body"))
        size = sum(f.stat().st_size for f in source.rglob("*") if f.is_file())
        print(f"| {source.name} | {len(bodies):,} | {size:,} |")
    print()


def report_packages() -> None:
    packages = Path(sysconfig.get_paths()["purelib"])
    size = sum(f.stat().st_size for f in packages.rglob("*") if f.is_file())
    print("## Installed packages\n")
    print(f"`site-packages` holds {size / 1e6:,.0f} MB.\n")


def report_workload(store: Path, args: argparse.Namespace) -> None:
    started = time.perf_counter()
    calendar.first_trading_day(args.start, 1)  # builds the NYSE calendar
    warm_up = time.perf_counter() - started

    opening = reading = 0.0
    decisions = reads = 0
    for day in first_trading_days(args.start, args.end):
        tickers = tickers_on(day)
        started = time.perf_counter()
        view = PointInTimeView(calendar.session_open(day), store=store)
        opened = time.perf_counter()
        with view:
            view.get_macro_as_of("UNRATE")
            for i in range(args.tickers):
                ticker = tickers[i % len(tickers)]
                view.get_price_history_as_of(ticker, args.lookback)
                view.get_latest_filing_as_of(ticker, "10-Q")
            reads += 1 + 2 * args.tickers
        finished = time.perf_counter()
        opening += opened - started
        reading += finished - opened
        decisions += 1

    total = opening + reading
    print("## A backtest-shaped workload\n")
    print(
        f"{decisions} monthly decisions, {args.start}–{args.end}, each reading "
        f"{args.tickers} tickers: {reads:,} reads in all.\n"
    )
    print("| Measure | Value |")
    print("| --- | ---: |")
    print(f"| Calendar warm-up | {warm_up:.2f} s |")
    each = opening / decisions * 1000
    print(f"| Opening views | {opening:.2f} s ({each:.1f} ms each) |")
    print(f"| Reading | {reading:.2f} s ({reading / reads * 1000:.2f} ms per read) |")
    print(f"| **Total** | **{total:.1f} s** ({total / decisions:.2f} s per decision) |")
    print(f"| Peak memory | {peak_memory_mb():.0f} MB |\n")


def first_trading_days(start: int, end: int) -> Iterator[date]:
    for year in range(start, end + 1):
        for month in range(1, 13):
            yield calendar.first_trading_day(year, month)


def tickers_on(day: date) -> list[str]:
    """The M2 ticker set's tickers in use on `day`, from the curated history."""
    tickers = []
    for security in CURATED.m2_ticker_set:
        current = [c for c in security.history if c.effective <= day]
        if current and current[-1].ticker is not None:
            tickers.append(current[-1].ticker)
    return tickers


def peak_memory_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports kibibytes.
    return peak / 1e6 if sys.platform == "darwin" else peak * 1024 / 1e6


if __name__ == "__main__":
    main()
