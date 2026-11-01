"""Standard metrics from XBRL facts, as known at a knowledge time (S5.6, S5.7).

Pure functions over `xbrl_facts` rows that a PointInTimeView has already read, so every
row they see was known at the knowledge time:

- `latest_by_period`: for each concept and period, the value its latest filing
  reported (doc/time-model.md, rule 6);
- `resolve`: for each period, the first concept in a metric's order that has a value;
- `quarterly_values`: a metric's quarters, reported or derived from year-to-date
  totals, with the concept and filings each came from;
- `coverage`: which of a company's 10-Qs and 10-Ks reported none of a metric's
  concepts for their own period.

Facts count only from 10-K, 10-Q, and 8-K filings and their amendments, the forms in
`filings`. Other forms, such as a proxy statement's pay-versus-performance table, repeat
numbers from those reports. They're stored (S5.5) but never read here, so a repeat
never stands in for the report.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
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


_SPANS = (
    (range(80, 101), 1),  # a quarter: 13 or 14 weeks, or 90 to 92 days
    (range(175, 197), 2),  # six months: 26 or 27 weeks, or 181 to 184 days
    (range(266, 288), 3),  # nine months: 39 or 40 weeks, or 273 to 275 days
    (range(350, 381), 4),  # a year: 52 or 53 weeks, or 365 or 366 days
)


def quarters_spanned(duration_days: int) -> int | None:
    """How many quarters a period covers, from its length in days, both ends counted:
    1 for a quarter, 2 for six months, 3 for nine months, and 4 for a year. None for
    anything else, such as an instant (0 days) or a transition period."""
    return next((n for days, n in _SPANS if duration_days in days), None)


@dataclass(frozen=True)
class Quarter:
    """A metric's value for one quarter as known by then, or, for an instant metric,
    for one date."""

    concept: str
    period_start: date | None
    period_end: date
    value: float
    derived: bool
    """Computed from two year-to-date totals rather than reported."""
    accession_numbers: tuple[str, ...]
    """The filings it came from; for a derived quarter, the longer total's first."""
    available_at: datetime
    """When the last of those filings was accepted."""
    time_assumed: bool
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    """"Q1" to "Q4"."""


def quarterly_values(
    rows: Iterable[Mapping[str, Any]], metric: Metric, concepts: Sequence[str]
) -> list[Quarter]:
    """Every quarter of a metric that `rows` give, oldest first.

    Periods are sorted by length (`quarters_spanned`), so 13- and 14-week quarters and
    52- and 53-week years count. For each quarter, keyed by its end date, the concepts
    are tried in order. A concept has the quarter if a filing reported it, or, for a
    metric that can be derived, if two of its year-to-date totals with the same start
    give it: Q2 is six months minus Q1, Q3 nine months minus six, and Q4 the year
    minus nine months. Every value is the latest one filed (`latest_by_period`), and a
    reported quarter beats a derived one. An instant metric has a value per date
    instead.

    Each value gets the fiscal year and quarter of the 10-Q or 10-K that reported its
    period as its own (`_labels`).
    """
    rows = list(rows)
    versions = latest_by_period(rows).versions
    found: dict[date, Quarter] = {}
    if metric.period == "instant":
        for (start, end), version in resolve(versions, concepts).items():
            if start is None:
                found[end] = _reported(version)
    else:
        for concept in concepts:
            for end, quarter in _quarters(versions, concept, metric.derive).items():
                found.setdefault(end, quarter)
    labels = _labels(rows)
    return [
        replace(found[end], fiscal_year=labels[end][0], fiscal_period=labels[end][1])
        if end in labels
        else found[end]
        for end in sorted(found)
    ]


def _quarters(
    versions: Mapping[ConceptPeriod, Version], concept: str, derive: bool
) -> dict[date, Quarter]:
    """One concept's quarters by end date: those reported, then, with `derive`, those
    its year-to-date totals give."""
    quarters: dict[date, Quarter] = {}
    totals: defaultdict[date, dict[int, Version]] = defaultdict(dict)
    for (name, start, end), version in versions.items():
        if name != concept or start is None:
            continue
        spanned = quarters_spanned((end - start).days + 1)
        if spanned is None:
            continue
        totals[start][spanned] = version  # by the fiscal year's start
        earlier = quarters.get(end)
        if spanned == 1 and (
            earlier is None or version.available_at > earlier.available_at
        ):
            quarters[end] = _reported(version)
    if derive:
        for by_span in totals.values():
            for spanned in (2, 3, 4):
                longer, shorter = by_span.get(spanned), by_span.get(spanned - 1)
                if longer is None or shorter is None:
                    continue
                start = shorter.period_end + timedelta(days=1)
                if quarters_spanned((longer.period_end - start).days + 1) == 1:
                    quarters.setdefault(longer.period_end, _derived(longer, shorter))
    return quarters


def _reported(version: Version) -> Quarter:
    return Quarter(
        concept=version.concept,
        period_start=version.period_start,
        period_end=version.period_end,
        value=version.value,
        derived=False,
        accession_numbers=(version.accession_number,),
        available_at=version.available_at,
        time_assumed=version.time_assumed,
    )


def _derived(longer: Version, shorter: Version) -> Quarter:
    """The quarter between two year-to-date totals with the same start."""
    return Quarter(
        concept=longer.concept,
        period_start=shorter.period_end + timedelta(days=1),
        period_end=longer.period_end,
        value=longer.value - shorter.value,
        derived=True,
        accession_numbers=tuple(
            dict.fromkeys((longer.accession_number, shorter.accession_number))
        ),
        available_at=max(longer.available_at, shorter.available_at),
        time_assumed=longer.time_assumed or shorter.time_assumed,
    )


def _labels(rows: Sequence[Mapping[str, Any]]) -> dict[date, tuple[int, str]]:
    """The fiscal year and quarter of each period end, from the 10-Qs and 10-Ks that
    reported it as their own period.

    SEC gives every fact its filing's fiscal year and period, so they're right only for
    the filing's own period: the latest period end it reported among `rows`. A 10-K's
    is the fourth quarter. The earliest such filing wins, so a comparative repeated in a
    later filing never relabels a period.
    """
    reports = [
        row
        for row in rows
        if form_family(row["form"] or "") in ("10-K", "10-Q")
        and row["fiscal_year"] is not None
        and row["fiscal_period"] in ("Q1", "Q2", "Q3", "Q4", "FY")
    ]
    own: dict[str, date] = {}
    for row in reports:
        accession = row["accession_number"]
        own[accession] = max(own.get(accession, row["period_end"]), row["period_end"])
    labels: dict[date, tuple[datetime, str, tuple[int, str]]] = {}
    for row in reports:
        end, accession = row["period_end"], row["accession_number"]
        if end != own[accession]:
            continue
        period = "Q4" if row["fiscal_period"] == "FY" else row["fiscal_period"]
        found = (row["available_at"], accession, (row["fiscal_year"], period))
        if end not in labels or found[:2] < labels[end][:2]:
            labels[end] = found
    return {end: label for end, (*_, label) in labels.items()}


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
