"""Standard metrics from XBRL facts, as known at a knowledge time (S5.6).

Pure functions over `xbrl_facts` rows that a PointInTimeView has already read, so every
row they see was known at the knowledge time:

- `latest_by_period`: for each concept and period, the value its latest filing
  reported (doc/time-model.md, rule 6);
- `resolve`: for each period, the first concept in a metric's order that has a value;
- `coverage`: which of a company's 10-Qs and 10-Ks reported none of a metric's
  concepts for their own period.

Facts count only from 10-K, 10-Q, and 8-K filings and their amendments, the forms in
`filings`. Other forms, such as a proxy statement's pay-versus-performance table, repeat
numbers from those reports. They're stored (S5.5) but never read here, so a repeat
never stands in for the report.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.data.records import ConceptUse
from app.data.sources.edgar import form_family
from app.data.sources.metrics import Metric

type Period = tuple[date | None, date]
"""A period's start and end. The start is None for an instant."""

type ConceptPeriod = tuple[str, date | None, date]
"""A concept, and a period's start and end."""


@dataclass(frozen=True)
class Version:
    """A concept's value for one period, as a filing reported it."""

    concept: str
    period_start: date | None
    period_end: date
    value: float
    accession_number: str
    form: str | None
    fiscal_year: int | None
    """The filing's fiscal year, as SEC gives it."""
    fiscal_period: str | None
    """The filing's fiscal period, such as "Q2" or "FY", as SEC gives it."""
    available_at: datetime
    """When the filing was accepted (rule 6)."""
    time_assumed: bool


@dataclass(frozen=True)
class Latest:
    """Each concept's latest value for each period, and where that was ambiguous."""

    versions: Mapping[ConceptPeriod, Version]
    ambiguous: tuple[Version, ...]
    """Periods whose latest filing reported two values for the concept, with one of
    them. They're left out of `versions`."""


def latest_by_period(rows: Iterable[Mapping[str, Any]]) -> Latest:
    """For each concept and period, the value the latest filing reported.

    Each filing counts once, at its earliest `available_at`. A fact stored first at the
    end of its filed date, because its filing wasn't in `filings` yet, and again once it
    was, became known at the earlier time. Of two filings known at the same moment, the
    larger accession number wins, so the result never depends on the order of rows.
    """
    copies: defaultdict[ConceptPeriod, defaultdict[str, list[Mapping[str, Any]]]]
    copies = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if form_family(row["form"] or "") is None:
            continue
        key = (row["concept"], row["period_start"], row["period_end"])
        copies[key][row["accession_number"]].append(row)

    versions: dict[ConceptPeriod, Version] = {}
    ambiguous: list[Version] = []
    for key, filings in copies.items():
        accession = max(
            filings,
            key=lambda number: (
                min(r["available_at"] for r in filings[number]),
                number,
            ),
        )
        reported = filings[accession]
        version = _version(min(reported, key=lambda row: row["available_at"]))
        if len({row["value"] for row in reported}) > 1:
            ambiguous.append(version)
        else:
            versions[key] = version
    return Latest(versions, tuple(sorted(ambiguous, key=_order)))


def resolve(
    versions: Mapping[ConceptPeriod, Version], concepts: Sequence[str]
) -> dict[Period, Version]:
    """For each period, the value of the first concept in `concepts` that has one.

    A company whose tag changed keeps one series, and each value keeps its concept.
    Microsoft's revenue for the quarter ended March 31, 2018 is its 10-Q's
    SalesRevenueNet until its fiscal 2018 10-K reports it as
    RevenueFromContractWithCustomerExcludingAssessedTax, which comes first.
    """
    rank = {concept: n for n, concept in enumerate(concepts)}
    resolved: dict[Period, Version] = {}
    for (concept, start, end), version in versions.items():
        if concept not in rank:
            continue
        best = resolved.get((start, end))
        if best is None or rank[concept] < rank[best.concept]:
            resolved[(start, end)] = version
    return resolved


@dataclass(frozen=True)
class Coverage:
    """How a metric's concepts cover a company's 10-Qs and 10-Ks."""

    filings_checked: int
    concepts_used: tuple[ConceptUse, ...]
    missing: tuple[date, ...]
    ambiguous: tuple[date, ...]


def coverage(
    filings: Iterable[Mapping[str, Any]],
    facts: Iterable[Mapping[str, Any]],
    metric: Metric,
    concepts: Sequence[str],
    since: datetime | None,
) -> Coverage:
    """Which of a company's 10-Qs and 10-Ks reported none of `concepts` for their own
    period, and which concept each of the others used.

    `filings` are the company's `filings` rows and `facts` its `xbrl_facts` rows.
    Original 10-Qs and 10-Ks accepted from `since` on are checked: the time of the
    company's first XBRL fact, since tagging began in 2009 to 2011. A filing covers the
    metric if it reported one of the concepts, in the metric's unit, for a period ending
    on its period of report; a cover-page concept (dei) needs only a value from it. It's
    ambiguous if it reported two values for the same period of the concept it used.
    """
    rank = {concept: n for n, concept in enumerate(concepts)}
    by_filing: defaultdict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for fact in facts:
        if fact["concept"] in rank and fact["unit"] == metric.unit:
            by_filing[fact["accession_number"]].append(fact)
    checked = sorted(
        (
            filing
            for filing in filings
            if since is not None
            and filing["available_at"] >= since
            and not filing["is_amendment"]
            and form_family(filing["form"]) in ("10-K", "10-Q")
            and filing["period_of_report"] is not None
        ),
        key=lambda filing: filing["period_of_report"],
    )

    used: defaultdict[str, list[date]] = defaultdict(list)
    missing: list[date] = []
    ambiguous: list[date] = []
    for filing in checked:
        period = filing["period_of_report"]
        own = [
            fact
            for fact in by_filing[filing["accession_number"]]
            if fact["concept"].startswith("dei:") or fact["period_end"] == period
        ]
        if not own:
            missing.append(period)
            continue
        concept = min({fact["concept"] for fact in own}, key=rank.__getitem__)
        used[concept].append(period)
        values: defaultdict[Period, set[float]] = defaultdict(set)
        for fact in own:
            if fact["concept"] == concept:
                values[(fact["period_start"], fact["period_end"])].add(fact["value"])
        if any(len(found) > 1 for found in values.values()):
            ambiguous.append(period)

    return Coverage(
        filings_checked=len(checked),
        concepts_used=tuple(
            ConceptUse(concept, len(periods), min(periods), max(periods))
            for concept, periods in sorted(used.items(), key=lambda item: rank[item[0]])
        ),
        missing=tuple(missing),
        ambiguous=tuple(ambiguous),
    )


def _version(row: Mapping[str, Any]) -> Version:
    return Version(
        concept=row["concept"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        value=row["value"],
        accession_number=row["accession_number"],
        form=row["form"],
        fiscal_year=row["fiscal_year"],
        fiscal_period=row["fiscal_period"],
        available_at=row["available_at"],
        time_assumed=row["time_assumed"],
    )


def _order(version: Version) -> tuple[str, date, date]:
    return (version.concept, version.period_end, version.period_start or date.min)
