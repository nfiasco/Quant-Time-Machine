"""SEC XBRL company facts: the numbers each company reported in its filings (S5.5).

`uv run python -m app.data.ingest sec` loads each company's facts right after its
filing history (sources/edgar.py), for every company whose submissions include XBRL
filings, from `api/xbrl/companyfacts/CIK##########.json`. Only the curated concepts in
CONCEPTS are kept, in every unit SEC gives: the revenue family, net income, diluted EPS,
operating cash flow, total assets, and shares outstanding.

**When a fact became public: the acceptance time of the filing that reported it**
(doc/time-model.md, rule 6). A fact's `filed` is a date only, so its accession number
(`accn`) is joined to that filing's corrected acceptance time, from the `filings` rows
the same run wrote. Companies repeat numbers, as comparatives in later filings and in
restatements, and each appearance is a row of its own, known from its own filing's
time. A fact whose filing isn't in `filings`, such as one from a proxy statement (DEF
14A), is known from the end of its filed date in New York, flagged `time_assumed`
(rule 11): a filing is never dated before it was accepted. A fact from a filing whose
time was assumed is flagged too.

**Never SEC's `frame`.** SEC puts it on the last-filed fact for each calendar period,
which no one knew at the time, so it isn't stored (doc/data-sources.md).

Only exact duplicates collapse. Two values one filing reported for the same period are
both kept, because the table's key includes the value.
"""

import logging
from collections.abc import Iterable, Mapping
from datetime import date, time
from typing import Any

from app.data.http import SourceClient
from app.data.sources import IngestContext
from app.data.store import WriteResult, write_rows
from app.data.tables import XBRL_FACTS
from app.data.timeutil import market_time

logger = logging.getLogger(__name__)

CONCEPTS: frozenset[str] = frozenset(
    {
        # Revenue, under its names before and after ASC 606, and banks' net revenue
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
        "us-gaap:Revenues",
        "us-gaap:SalesRevenueNet",
        "us-gaap:RevenuesNetOfInterestExpense",
        # Net income
        "us-gaap:NetIncomeLoss",
        "us-gaap:ProfitLoss",
        # Diluted earnings per share
        "us-gaap:EarningsPerShareDiluted",
        "us-gaap:EarningsPerShareBasicAndDiluted",
        # Operating cash flow
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
        "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        # Total assets
        "us-gaap:Assets",
        # Shares outstanding, from the cover page
        "dei:EntityCommonStockSharesOutstanding",
    }
)
"""The concepts kept, each with its taxonomy."""

END_OF_DAY = time(23, 59, 59, 999999)


def fetch_company_facts(client: SourceClient, cik: int) -> dict[str, Any]:
    """Every XBRL fact a company has filed, as SEC's company facts API gives them."""
    return client.get(f"api/xbrl/companyfacts/CIK{cik:010d}.json").json()


def fact_rows(
    cik: int,
    company_facts: Mapping[str, Any],
    filings: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """`xbrl_facts` rows for a company's facts in the curated concepts.

    `filings` maps each accession number to its `filings` row. A fact takes on its
    filing's `available_at` and `time_assumed`, or the end of its filed date, flagged,
    when its filing isn't there.
    """
    rows = []
    for taxonomy, concepts in company_facts.get("facts", {}).items():
        for name, concept in concepts.items():
            if f"{taxonomy}:{name}" not in CONCEPTS:
                continue
            for unit, facts in concept.get("units", {}).items():
                rows.extend(
                    _fact_row(cik, f"{taxonomy}:{name}", unit, fact, filings)
                    for fact in facts
                )
    return rows


def _fact_row(
    cik: int,
    concept: str,
    unit: str,
    fact: Mapping[str, Any],
    filings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    start = date.fromisoformat(fact["start"]) if fact.get("start") else None
    end = date.fromisoformat(fact["end"])
    filed = date.fromisoformat(fact["filed"])
    filing = filings.get(fact["accn"])
    if filing is None:
        available_at, time_assumed = market_time(filed, END_OF_DAY), True
    else:
        available_at, time_assumed = filing["available_at"], filing["time_assumed"]
    return {
        "cik": cik,
        "accession_number": fact["accn"],
        "concept": concept,
        "unit": unit,
        "period_start": start,
        "period_end": end,
        "duration_days": 0 if start is None else (end - start).days + 1,
        "value": float(fact["val"]),
        "fiscal_year": fact.get("fy"),
        "fiscal_period": fact.get("fp"),
        "form": fact.get("form"),
        "filed": filed,
        "source": "edgar",
        "source_ref": fact["accn"],
        "available_at": available_at,
        "time_assumed": time_assumed,
    }


def ingest_facts(
    context: IngestContext,
    security_id: str,
    cik: int,
    filings: Iterable[Mapping[str, Any]],
) -> WriteResult:
    """Load a company's facts in the curated concepts, each known when the filing that
    reported it was accepted. `filings` are the company's `filings` rows."""
    by_accession = {filing["accession_number"]: filing for filing in filings}
    rows = fact_rows(cik, fetch_company_facts(context.client, cik), by_accession)
    result = write_rows(context.store, XBRL_FACTS, rows)
    logger.info(
        "%s (CIK %d): %d facts in the curated concepts, %d new, %d with assumed times",
        security_id,
        cik,
        len(rows),
        result.written,
        sum(1 for row in rows if row["time_assumed"]),
    )
    return result
