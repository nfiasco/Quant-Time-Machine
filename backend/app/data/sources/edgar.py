"""SEC EDGAR filing histories (S5.3).

`uv run python -m app.data.ingest sec` loads company identity and universe membership
first (sources/securities.py and sources/universes.py), then the filing history of each
universe member and benchmark, AAPL first, into the `filings` table. A history is `submissions/CIK##########.json`, whose
`recent` block holds the last year or so (at least 1,000 filings), plus every older
page listed in its `filings.files`. All requests stay within SEC's limit of 10 per
second. Only 10-K, 10-Q, and 8-K filings and their amendments are kept: JPMorgan alone
has over 160,000 filings, nearly all structured-note prospectuses.

**When a filing became public: its EDGAR acceptance time** (doc/time-model.md, rule 5).
In most companies' files, `acceptanceDateTime` ends in Z but runs ahead of the true
time by the Eastern UTC offset: 4 hours in EDT, 5 in EST. EDGAR's index pages confirm
this for Apple, Microsoft, JPMorgan, and Meta from 2006 to 2026. Twitter's file holds
true UTC times, though, so each company's file is checked. A filing's date follows from
its acceptance time (accepted after 5:30 PM ET, it's dated the next business day), and
EDGAR is open only from 06:00 to 22:00 ET. So every filing whose date only one reading
explains is a vote, and the majority decides. A file without any votes is taken to run
ahead, like most.

A time that still can't be right is replaced with the end of the filing date in New
York, or kept if it's later than that, and flagged `time_assumed` (rule 11). That
covers a missing time; the midnight placeholders EDGAR recorded for many filings from
1994 to 2002, when it kept only a date; and a time outside EDGAR's hours or after the
filing date.

**Amendments.** A form ending in /A amends the latest original of the same kind, for
the same company and period of report, accepted before it, when there is one.
"""

import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

from app.data.http import SourceClient
from app.data.sources import IngestContext, securities, universes
from app.data.store import write_rows
from app.data.tables import FILINGS
from app.data.timeutil import ET, market_time

logger = logging.getLogger(__name__)

FORM_FAMILIES: Mapping[str, tuple[str, ...]] = {
    "10-K": ("10-K", "10-K405", "10-KT"),
    "10-Q": ("10-Q", "10-QT"),
    "8-K": ("8-K",),
}
"""The forms kept, by the family a reader asks for. Each one's amendment (/A) is kept
too."""

EDGAR_OPENS, EDGAR_CLOSES = time(6, 0), time(22, 0)
"""EDGAR accepts filings only between these New York times, on business days."""

FILING_DATE_CUTOFF = time(17, 30)
"""A filing accepted after this New York time is dated the next business day
(Regulation S-T, Rule 13)."""

END_OF_DAY = time(23, 59, 59, 999999)


def form_family(form: str) -> str | None:
    """The family a form belongs to, such as "10-K" for "10-K405/A", or None."""
    base = form.removesuffix("/A")
    return next((f for f, forms in FORM_FAMILIES.items() if base in forms), None)


def corrected_acceptance(raw: str) -> datetime:
    """An `acceptanceDateTime` that runs ahead by the Eastern offset, as true UTC.

    "2020-05-01T02:03:10.000Z" was accepted at 18:03:10 EDT on April 30, so this
    returns 2020-04-30T22:03:10Z. The offset is taken at the shown time, which matches
    the true time's: EDGAR is closed overnight and on weekends, and clocks change at
    02:00 on Sundays.
    """
    shown = datetime.fromisoformat(raw)
    offset = shown.astimezone(ET).utcoffset()
    assert offset is not None
    return shown + offset


def ingest(context: IngestContext) -> None:
    """Load company identity and universe membership, then the filing histories of the
    universes' members and the benchmarks, AAPL first."""
    securities.ingest(context)
    universes.write_members(context.store)
    for security in universes.ingest_set():
        for cik in security.ciks:
            filings = fetch_filings(context.client, cik)
            shifted, votes = runs_ahead(filings)
            rows = filing_rows(cik, filings, shifted=shifted)
            result = write_rows(context.store, FILINGS, rows)
            logger.info(
                "%s (CIK %d): %d filings, %d kept, %d new, %d with assumed times; "
                "acceptance times %s, by a vote of %d to %d",
                security.id,
                cik,
                len(filings),
                len(rows),
                result.written,
                sum(1 for row in rows if row["time_assumed"]),
                "run ahead by the Eastern offset" if shifted else "are true UTC",
                *(votes if shifted else reversed(votes)),
            )


def fetch_filings(client: SourceClient, cik: int) -> list[dict[str, Any]]:
    """Every filing in a company's submissions, from the recent block and older pages."""
    submissions = client.get(f"submissions/CIK{cik:010d}.json").json()
    blocks = [submissions["filings"]["recent"]]
    for page in submissions["filings"].get("files", ()):
        blocks.append(client.get(f"submissions/{page['name']}").json())
    filings: dict[str, dict[str, Any]] = {}
    for block in blocks:
        for values in zip(*block.values(), strict=True):
            filing = dict(zip(block, values, strict=True))
            filings.setdefault(filing["accessionNumber"], filing)
    return list(filings.values())


def runs_ahead(filings: Iterable[Mapping[str, Any]]) -> tuple[bool, tuple[int, int]]:
    """Whether a company's acceptance times run ahead by the Eastern offset, and the
    votes: filings that only the shifted reading explains, then only the shown one."""
    ahead = as_shown = 0
    for filing in filings:
        raw = filing["acceptanceDateTime"]
        if form_family(filing["form"]) is None or not raw:
            continue
        shown = datetime.fromisoformat(raw)
        if (shown.minute, shown.second, shown.microsecond) == (0, 0, 0):
            continue  # a date-only placeholder says nothing about the shift
        filed = date.fromisoformat(filing["filingDate"])
        shifted_fits = _explains(corrected_acceptance(raw), filed)
        shown_fits = _explains(shown, filed)
        ahead += shifted_fits and not shown_fits
        as_shown += shown_fits and not shifted_fits
    return ahead >= as_shown, (ahead, as_shown)


def _explains(accepted: datetime, filed: date) -> bool:
    """Whether an acceptance time is within EDGAR's hours and gives this filing date."""
    local = accepted.astimezone(ET)
    if not EDGAR_OPENS <= local.time() <= EDGAR_CLOSES:
        return False
    day = local.date()
    if local.time() > FILING_DATE_CUTOFF:
        # The next weekday. Federal holidays are ignored, so a filing just before one
        # can lose its vote; the majority absorbs that.
        day += timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
    return day == filed


def acceptance(raw: str, filed: date, *, shifted: bool) -> tuple[datetime, bool]:
    """When a filing became public, and whether that time was assumed.

    The acceptance time, if it's within EDGAR's hours and on the filing date or a few
    days before it. Otherwise the end of the filing date in New York, or the acceptance
    time if that's later, flagged as assumed.
    """
    end_of_filing_date = market_time(filed, END_OF_DAY)
    if not raw:
        return end_of_filing_date, True
    accepted = corrected_acceptance(raw) if shifted else datetime.fromisoformat(raw)
    local = accepted.astimezone(ET)
    plausible = (
        EDGAR_OPENS <= local.time() <= EDGAR_CLOSES
        and filed - timedelta(days=5) <= local.date() <= filed
    )
    if plausible:
        return accepted, False
    return max(accepted, end_of_filing_date), True


def filing_rows(
    cik: int, filings: Iterable[Mapping[str, Any]], *, shifted: bool
) -> list[dict[str, Any]]:
    """`filings` rows for a company's 10-K, 10-Q, and 8-K filings and amendments."""
    rows: list[dict[str, Any]] = []
    for filing in filings:
        form = filing["form"]
        if form_family(form) is None:
            continue
        filed = date.fromisoformat(filing["filingDate"])
        raw = filing["acceptanceDateTime"]
        available_at, time_assumed = acceptance(raw, filed, shifted=shifted)
        report = filing.get("reportDate") or None
        rows.append(
            {
                "cik": cik,
                "accession_number": filing["accessionNumber"],
                "form": form,
                "filing_date": filed,
                "period_of_report": date.fromisoformat(report) if report else None,
                "is_amendment": form.endswith("/A"),
                "amends": None,
                "primary_document": filing.get("primaryDocument") or None,
                "items": filing.get("items") or None,
                "acceptance_raw": raw or None,
                "source": "edgar",
                "source_ref": filing["accessionNumber"],
                "available_at": available_at,
                "time_assumed": time_assumed,
            }
        )
    link_amendments(rows)
    return rows


def link_amendments(rows: Sequence[dict[str, Any]]) -> None:
    """Set each amendment's `amends` to the latest original of the same family and
    period of report accepted before it, if there's one."""
    originals: dict[tuple[str | None, date], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not row["is_amendment"] and row["period_of_report"] is not None:
            originals[(form_family(row["form"]), row["period_of_report"])].append(row)
    for row in rows:
        if not row["is_amendment"] or row["period_of_report"] is None:
            continue
        earlier = [
            original
            for original in originals[
                (form_family(row["form"]), row["period_of_report"])
            ]
            if original["available_at"] < row["available_at"]
        ]
        if earlier:
            latest = max(earlier, key=lambda original: original["available_at"])
            row["amends"] = latest["accession_number"]
