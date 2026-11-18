"""Print where a universe's prices and fundamentals have gaps (S5.6, S6.7). From
backend/:

    uv run python -m app.data.coverage [--as-of 2026-11-01] [--metric revenue]

It reads the store as the API does, pinned to the newest data version, as known at
`--as-of` (default: now), and prints Markdown about every company that was ever in the
universe:

- **Gaps by company and year:** the sessions it had no bar for, or a bar without
  trades, and the periods no concept of a metric covered, side by side.
- **Prices:** its memberships, the sessions it should have traded in (while a member,
  until it stopped trading), how many were missing or had no trades, and its last
  trade.
- **One section for each metric:** how many of its 10-Qs and 10-Ks were checked, from
  its first XBRL fact on, which concepts they used, and which periods none of the
  concepts covered. A company that misses periods, or whose concept switches to one
  with different values, may need an override in app/data/sources/metrics.toml.

Each backtest run reports the gaps its own decisions met (app/backtest/coverage.py).
"""

import argparse
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime

from app.config import get_settings
from app.data import calendar
from app.data.errors import NotFoundError
from app.data.records import FundamentalsCoverage, PriceCoverage
from app.data.sources.metrics import METRICS
from app.data.store import store_dir
from app.data.timeutil import KnowledgeTimeError, describe_time, parse_knowledge_time
from app.data.versions import latest_data_version
from app.data.view import PointInTimeView


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.data.coverage",
        description="Print where a universe's prices and fundamentals have gaps.",
    )
    parser.add_argument(
        "--as-of", help="the knowledge time, written as the API's as_of (default: now)"
    )
    parser.add_argument("--universe", default="starter_large_caps")
    parser.add_argument(
        "--metric",
        action="append",
        choices=list(METRICS),
        help="a metric to check; repeat it for more (default: every metric)",
    )
    args = parser.parse_args(argv)
    try:
        knowledge_time = (
            datetime.now(UTC)
            if args.as_of is None
            else parse_knowledge_time(args.as_of)
        )
    except KnowledgeTimeError as error:
        print(error, file=sys.stderr)
        return 2

    store = store_dir(get_settings().data_dir)
    with PointInTimeView(
        knowledge_time, data_version=latest_data_version(store), store=store
    ) as view:
        try:
            print(report(view, args.universe, args.metric or list(METRICS)))
        except NotFoundError as error:
            print(f"No such universe: {error.ident}", file=sys.stderr)
            return 2
    return 0


def report(view: PointInTimeView, universe: str, metrics: Iterable[str]) -> str:
    """The coverage of `universe`'s prices and of each metric in `metrics`, as
    Markdown."""
    prices = view.price_coverage(universe)
    fundamentals = {
        metric: view.fundamentals_coverage(universe, metric) for metric in metrics
    }
    lines = [
        "# Coverage",
        "",
        (
            f"`{universe}` as known at {describe_time(view.knowledge_time)}, data "
            f"version {view.data_version}, for every company that was ever a member. "
            "Prices: the sessions it should have traded in, while a member and until "
            "it stopped trading. Fundamentals: its original 10-Qs and 10-Ks from its "
            "first XBRL fact on."
        ),
        "",
        *_gaps(prices, fundamentals),
        "",
        *_prices(prices),
    ]
    for metric, companies in fundamentals.items():
        lines += ["", *_section(metric, companies)]
    return "\n".join(lines)


def _gaps(
    prices: Sequence[PriceCoverage],
    fundamentals: Mapping[str, Sequence[FundamentalsCoverage]],
) -> list[str]:
    """Each company's gaps in prices and in each metric, by calendar year: the year of
    a session, or of a period of report."""
    found: defaultdict[tuple[str, int], dict[str, list[str]]] = defaultdict(
        lambda: {"prices": [], "fundamentals": []}
    )
    for company in prices:
        for label, days in (
            ("missing", company.missing),
            ("without trades", company.no_trades),
        ):
            for year, group in _by_year(days).items():
                found[(company.security_id, year)]["prices"].append(
                    f"{len(group):,} {label}: {_ranges(group)}"
                )
    for metric, companies in fundamentals.items():
        for company in companies:
            for year, group in _by_year(company.missing).items():
                periods = ", ".join(str(period) for period in group)
                found[(company.security_id, year)]["fundamentals"].append(
                    f"{metric}: {periods}"
                )

    lines = ["## Gaps by company and year", ""]
    if not found:
        return [*lines, "No company missed a session or a period."]
    names = {company.security_id: company.name for company in prices}
    lines += [
        "| Company | Year | Prices | Fundamentals |",
        "| --- | ---: | --- | --- |",
    ]
    for (security_id, year), gaps in sorted(found.items()):
        lines.append(
            f"| {names.get(security_id, security_id)} (`{security_id}`) | {year} "
            f"| {'; '.join(gaps['prices'])} | {'; '.join(gaps['fundamentals'])} |"
        )
    return lines


def _prices(companies: Sequence[PriceCoverage]) -> list[str]:
    """How each company's daily bars cover the sessions it should have traded in."""
    lines = [
        "## Prices",
        "",
        (
            "| Company | Member | Sessions | Missing | No trades | Last trade "
            "| Stopped trading |"
        ),
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for company in companies:
        member = "; ".join(
            f"{added} on" if removed is None else f"{added} to {removed}"
            for added, removed in company.spells
        )
        lines.append(
            f"| {company.name} (`{company.security_id}`) | {member} "
            f"| {company.sessions:,} | {len(company.missing):,} "
            f"| {len(company.no_trades):,} | {company.last_traded or 'none'} "
            f"| {company.stopped_trading or ''} |"
        )
    return lines


def _by_year(days: Iterable[date]) -> dict[int, list[date]]:
    """Dates grouped by calendar year, in order."""
    years: defaultdict[int, list[date]] = defaultdict(list)
    for day in sorted(days):
        years[day.year].append(day)
    return dict(years)


def _ranges(sessions: Sequence[date]) -> str:
    """Sessions, with each run of consecutive ones written as its first and last:
    "2019-11-21, 2020-01-02 to 2020-01-06"."""
    runs: list[list[date]] = []
    for session in sessions:
        if runs and calendar.next_session(runs[-1][-1]) == session:
            runs[-1].append(session)
        else:
            runs.append([session])
    return ", ".join(
        str(run[0]) if len(run) == 1 else f"{run[0]} to {run[-1]}" for run in runs
    )


def _section(metric: str, companies: Sequence[FundamentalsCoverage]) -> list[str]:
    lines = [
        f"## {metric}",
        "",
        "| Company | Filings | Missing | Concepts used |",
        "| --- | ---: | ---: | --- |",
    ]
    for company in companies:
        used = "; ".join(
            f"`{use.concept}`: {use.filings} ({use.first_period} to {use.last_period})"
            for use in company.concepts_used
        )
        lines.append(
            f"| {company.name} (`{company.security_id}`) | {company.filings_checked} "
            f"| {len(company.missing)} | {used or 'none'} |"
        )
    for label, attribute in (("Missing", "missing"), ("Ambiguous", "ambiguous")):
        gaps = [c for c in companies if getattr(c, attribute)]
        lines += ["", f"{label} periods:" if gaps else f"{label} periods: none."]
        if gaps:
            lines.append("")
        lines += [
            f"- `{c.security_id}`: "
            + ", ".join(str(period) for period in getattr(c, attribute))
            for c in gaps
        ]
    return lines


if __name__ == "__main__":
    sys.exit(main())
