from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.data.errors import NotFoundError
from app.data.fundamentals import (
    Period,
    Version,
    coverage,
    latest_by_period,
    resolve,
)
from app.data.records import ConceptUse
from app.data.sources import securities, universes
from app.data.sources.metrics import METRICS
from app.data.store import write_rows
from app.data.tables import FILINGS, SECURITIES, UNIVERSE_MEMBERS, XBRL_FACTS
from app.data.timeutil import parse_knowledge_time
from app.data.view import PointInTimeView

REVENUE = METRICS["revenue"]
NEW_REVENUE = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
SALES = "us-gaap:SalesRevenueNet"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def fact(
    concept: str,
    period: Period,
    value: float,
    accession: str,
    available_at: datetime,
    *,
    form: str = "10-Q",
    unit: str = "USD",
    time_assumed: bool = False,
    cik: int = 320193,
) -> dict[str, Any]:
    """An `xbrl_facts` row as a view returns it."""
    start, end = period
    return {
        "cik": cik,
        "accession_number": accession,
        "concept": concept,
        "unit": unit,
        "period_start": start,
        "period_end": end,
        "duration_days": 0 if start is None else (end - start).days + 1,
        "value": value,
        "fiscal_year": None,
        "fiscal_period": None,
        "form": form,
        "filed": available_at.date(),
        "source": "edgar",
        "source_ref": accession,
        "available_at": available_at,
        "time_assumed": time_assumed,
    }


QUARTER = (date(2019, 12, 29), date(2020, 3, 28))


def test_the_latest_filing_wins_for_each_concept_and_period() -> None:
    rows = [
        fact(NEW_REVENUE, QUARTER, 58313e6, "10-Q", utc(2020, 4, 30, 22)),
        fact(NEW_REVENUE, QUARTER, 58000e6, "10-K/A", utc(2020, 12, 1), form="10-K/A"),
        fact(SALES, QUARTER, 58313e6, "older", utc(2020, 4, 30, 22)),
    ]

    versions = latest_by_period(rows).versions

    assert versions[(NEW_REVENUE, *QUARTER)].accession_number == "10-K/A"
    assert versions[(NEW_REVENUE, *QUARTER)].value == 58000e6
    assert versions[(SALES, *QUARTER)].accession_number == "older"


def test_a_filing_counts_once_from_its_earliest_time() -> None:
    # The 10-Q was stored first at the end of its filed date, before its filing reached
    # `filings`, and again at its acceptance time. It counts from the acceptance, so the
    # 8-K accepted in between is the latest.
    rows = [
        fact(
            NEW_REVENUE, QUARTER, 1.0, "10-Q", utc(2020, 5, 2, 3, 59), time_assumed=True
        ),
        fact(NEW_REVENUE, QUARTER, 1.0, "10-Q", utc(2020, 4, 30, 22)),
        fact(NEW_REVENUE, QUARTER, 2.0, "8-K", utc(2020, 5, 1, 12), form="8-K"),
    ]

    latest = latest_by_period(rows).versions[(NEW_REVENUE, *QUARTER)]
    alone = latest_by_period(rows[:2]).versions[(NEW_REVENUE, *QUARTER)]

    assert latest.accession_number == "8-K"
    assert (alone.available_at, alone.time_assumed) == (utc(2020, 4, 30, 22), False)


def test_filings_known_at_the_same_moment_are_ordered_by_accession_number() -> None:
    rows = [
        fact(NEW_REVENUE, QUARTER, 1.0, "0000000001-20-000002", utc(2020, 5, 2)),
        fact(NEW_REVENUE, QUARTER, 2.0, "0000000001-20-000001", utc(2020, 5, 2)),
    ]

    for order in (rows, rows[::-1]):
        version = latest_by_period(order).versions[(NEW_REVENUE, *QUARTER)]
        assert version.accession_number == "0000000001-20-000002"


def test_two_values_from_the_latest_filing_are_ambiguous() -> None:
    rows = [
        fact(NEW_REVENUE, QUARTER, 1.0, "older", utc(2020, 4, 30)),
        fact(NEW_REVENUE, QUARTER, 2.0, "newer", utc(2020, 5, 30)),
        fact(NEW_REVENUE, QUARTER, 3.0, "newer", utc(2020, 5, 30)),
    ]

    latest = latest_by_period(rows)

    assert latest.versions == {}
    assert [v.accession_number for v in latest.ambiguous] == ["newer"]


def test_facts_from_other_forms_are_never_read() -> None:
    # A proxy statement repeats the 10-K's net income in its pay-versus-performance
    # table, later; the 10-K stays the latest report.
    year = (date(2021, 7, 1), date(2022, 6, 30))
    rows = [
        fact(
            "us-gaap:NetIncomeLoss",
            year,
            72738e6,
            "10-K",
            utc(2022, 7, 28),
            form="10-K",
        ),
        fact(
            "us-gaap:NetIncomeLoss",
            year,
            72738e6,
            "proxy",
            utc(2026, 10, 22, 3, 59),
            form="DEF 14A",
            time_assumed=True,
        ),
    ]

    [version] = latest_by_period(rows).versions.values()

    assert version.accession_number == "10-K"


def test_each_period_takes_the_first_concept_that_has_a_value() -> None:
    earlier = (date(2017, 12, 31), date(2018, 3, 31))
    rows = [
        fact(SALES, QUARTER, 1.0, "a", utc(2020, 4, 30)),
        fact(NEW_REVENUE, QUARTER, 2.0, "b", utc(2020, 4, 30)),
        fact(SALES, earlier, 3.0, "c", utc(2018, 4, 30)),
    ]

    resolved = resolve(latest_by_period(rows).versions, REVENUE.concepts)

    assert {period: (v.concept, v.value) for period, v in resolved.items()} == {
        QUARTER: (NEW_REVENUE, 2.0),
        earlier: (SALES, 3.0),
    }


def revenue(store: Path, as_of: str, cik: int, concepts: tuple[str, ...]) -> Version:
    """The revenue `concepts` resolve to for a company's only fixture quarter."""
    with PointInTimeView(parse_knowledge_time(as_of), store=store) as view:
        rows = view._select("xbrl_facts", where="cik = ?", params=[cik])
    [version] = resolve(latest_by_period(rows).versions, concepts).values()
    return version


def test_a_revenue_tag_that_changed_with_asc_606(fixture_store: Path) -> None:
    # Microsoft's revenue for the quarter ended March 31, 2018: SalesRevenueNet in its
    # 10-Q, then the ASC 606 name in its fiscal 2018 10-K, accepted on August 3, 2018.
    concepts = REVENUE.concepts_for("microsoft")
    before = revenue(fixture_store, "2018-08-03T09:30", 789019, concepts)
    after = revenue(fixture_store, "2018-08-03T11:05", 789019, concepts)

    assert (before.concept, before.accession_number, before.value) == (
        SALES,
        "0001564590-18-009307",
        26819e6,
    )
    assert (after.concept, after.accession_number, after.value) == (
        NEW_REVENUE,
        "0001564590-18-019062",
        26819e6,
    )


def test_jpmorgan_needs_its_override_to_see_its_recast(fixture_store: Path) -> None:
    # JPMorgan's first quarter of 2014: $22,993 million as Revenues in its 10-Q, and
    # $23,215 million as recast, tagged RevenuesNetOfInterestExpense, a year later.
    override = REVENUE.concepts_for("jpmorgan")

    first = revenue(fixture_store, "2014-06-02", 19617, override)
    recast = revenue(fixture_store, "2015-06-01", 19617, override)
    default = revenue(fixture_store, "2015-06-01", 19617, REVENUE.concepts)

    assert (first.concept, first.value) == ("us-gaap:Revenues", 22993e6)
    assert (recast.concept, recast.value) == (
        "us-gaap:RevenuesNetOfInterestExpense",
        23215e6,
    )
    assert (default.concept, default.value) == ("us-gaap:Revenues", 22993e6)


def made_up_filing(
    accession: str, form: str, period: date, accepted: datetime
) -> dict[str, Any]:
    return {
        "cik": 320193,
        "accession_number": accession,
        "form": form,
        "filing_date": accepted.date(),
        "period_of_report": period,
        "is_amendment": form.endswith("/A"),
        "amends": None,
        "primary_document": None,
        "items": None,
        "acceptance_raw": None,
        "source": "edgar",
        "source_ref": f"made up: {accession}",
        "available_at": accepted,
        "time_assumed": False,
    }


# Made-up Apple filings around XBRL's start: the 10-Q for the quarter ended June 2008
# predates its first fact, and the 10-Q/A isn't checked.
FILINGS_2009 = [
    made_up_filing("Q3-2008", "10-Q", date(2008, 6, 28), utc(2008, 7, 23, 20)),
    made_up_filing("Q3-2009", "10-Q", date(2009, 6, 27), utc(2009, 7, 22, 20)),
    made_up_filing("FY-2009", "10-K", date(2009, 9, 26), utc(2009, 10, 27, 20)),
    made_up_filing("Q1-2010", "10-Q", date(2009, 12, 26), utc(2010, 1, 25, 20)),
    made_up_filing("Q1-2010A", "10-Q/A", date(2009, 12, 26), utc(2010, 2, 1, 20)),
]
FACTS_2009 = [
    fact(
        SALES,
        (date(2009, 3, 29), date(2009, 6, 27)),
        8337e6,
        "Q3-2009",
        utc(2009, 7, 22, 20),
    ),
    fact(
        SALES,
        (date(2008, 9, 28), date(2009, 9, 26)),
        36537e6,
        "FY-2009",
        utc(2009, 10, 27, 20),
        form="10-K",
    ),
    # The 10-Q for the first quarter of fiscal 2010 tagged no revenue concept, and
    # reported total assets twice.
    fact(
        "us-gaap:Assets",
        (None, date(2009, 12, 26)),
        1.0,
        "Q1-2010",
        utc(2010, 1, 25, 20),
    ),
    fact(
        "us-gaap:Assets",
        (None, date(2009, 12, 26)),
        2.0,
        "Q1-2010",
        utc(2010, 1, 25, 20),
    ),
    fact(
        "dei:EntityCommonStockSharesOutstanding",
        (None, date(2010, 1, 15)),
        906794000.0,
        "Q1-2010",
        utc(2010, 1, 25, 20),
        unit="shares",
    ),
]


def test_coverage_lists_filings_without_a_listed_concept() -> None:
    since = utc(2009, 7, 22, 20)  # the first fact

    found = coverage(FILINGS_2009, FACTS_2009, REVENUE, REVENUE.concepts, since)

    assert found.filings_checked == 3
    assert found.missing == (date(2009, 12, 26),)
    assert found.concepts_used == (
        ConceptUse(SALES, 2, date(2009, 6, 27), date(2009, 9, 26)),
    )
    assert found.ambiguous == ()


def test_coverage_of_instants() -> None:
    since = utc(2009, 7, 22, 20)
    assets = METRICS["total_assets"]
    shares = METRICS["shares_outstanding"]

    on_balance_sheet = coverage(
        FILINGS_2009, FACTS_2009, assets, assets.concepts, since
    )
    on_cover = coverage(FILINGS_2009, FACTS_2009, shares, shares.concepts, since)

    assert on_balance_sheet.missing == (date(2009, 6, 27), date(2009, 9, 26))
    assert on_balance_sheet.ambiguous == (date(2009, 12, 26),)
    # A cover's count is dated after the period, so any value from the filing counts.
    assert on_cover.missing == (date(2009, 6, 27), date(2009, 9, 26))
    assert on_cover.concepts_used == (
        ConceptUse(
            "dei:EntityCommonStockSharesOutstanding",
            1,
            date(2009, 12, 26),
            date(2009, 12, 26),
        ),
    )


def test_fundamentals_coverage_reads_every_member_by_the_knowledge_time(
    store_dir: Path,
) -> None:
    write_rows(store_dir, SECURITIES, securities.curated_rows(securities.CURATED))
    write_rows(store_dir, UNIVERSE_MEMBERS, universes.membership_rows())
    write_rows(store_dir, FILINGS, FILINGS_2009)
    write_rows(store_dir, XBRL_FACTS, FACTS_2009)

    with PointInTimeView(utc(2011, 1, 1), store=store_dir) as view:
        report = {
            c.security_id: c
            for c in view.fundamentals_coverage("starter_large_caps", "revenue")
        }
        with pytest.raises(NotFoundError):
            view.fundamentals_coverage("sp500", "revenue")
        with pytest.raises(ValueError, match="unknown metric"):
            view.fundamentals_coverage("starter_large_caps", "ebitda")

    apple = report["apple"]
    assert (apple.name, apple.filings_checked, apple.missing) == (
        "Apple Inc.",
        3,
        (date(2009, 12, 26),),
    )
    assert apple.concepts == REVENUE.concepts
    assert report["microsoft"].filings_checked == 0  # no facts in this store
    assert "tesla" not in report  # it joined on 2020-12-21
    assert report["jpmorgan"].concepts == REVENUE.concepts_for("jpmorgan")
