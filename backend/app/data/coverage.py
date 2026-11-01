"""Print how well the standard metrics' XBRL concepts cover a universe (S5.6). From
backend/:

    uv run python -m app.data.coverage [--as-of 2026-11-01] [--metric revenue]

It reads the store as the API does, pinned to the newest data version, as known at
`--as-of` (default: now), and prints Markdown. For each metric, every company that was
ever in the universe gets a row: how many of its 10-Qs and 10-Ks were checked, from its
first XBRL fact on, which concepts they used, and which periods none of the concepts
covered. A company that misses periods, or whose concept switches to one with different
values, may need an override in app/data/sources/metrics.toml.
"""

import argparse
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from app.config import get_settings
from app.data.errors import NotFoundError
from app.data.records import FundamentalsCoverage
from app.data.sources.metrics import METRICS
from app.data.store import store_dir
from app.data.timeutil import KnowledgeTimeError, describe_time, parse_knowledge_time
from app.data.versions import latest_data_version
from app.data.view import PointInTimeView


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.data.coverage",
        description="Print how well the standard metrics cover a universe's filings.",
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
    """The coverage of each metric in `metrics` for `universe`, as Markdown."""
    lines = [
        "# Fundamentals coverage",
        "",
        (
            f"`{universe}` as known at {describe_time(view.knowledge_time)}, data "
            f"version {view.data_version}: each company's original 10-Qs and 10-Ks "
            "from its first XBRL fact on."
        ),
    ]
    for metric in metrics:
        lines += ["", *_section(metric, view.fundamentals_coverage(universe, metric))]
    return "\n".join(lines)


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
