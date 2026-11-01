from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.data.errors import NotFoundError
from app.data.fundamentals import (
    Period,
    Quarter,
    Version,
    coverage,
    latest_by_period,
    quarterly_values,
    quarters_spanned,
    resolve,
)
from app.data.records import ConceptUse, Fundamental
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


# S5.7: quarters as known at a time


@pytest.mark.parametrize(
    ("days", "spanned"),
    [
        (91, 1),  # 13 weeks
        (98, 1),  # 14 weeks: Apple's first quarter in a 53-week year
        (90, 1),
        (92, 1),
        (182, 2),
        (189, 2),
        (273, 3),
        (280, 3),
        (364, 4),
        (371, 4),  # 53 weeks
        (365, 4),
        (0, None),  # an instant
        (120, None),
        (400, None),
    ],
)
def test_periods_are_sorted_by_length(days: int, spanned: int | None) -> None:
    assert quarters_spanned(days) == spanned


def values(quarters: list[Quarter]) -> list[tuple[date | None, date, float, bool]]:
    return [(q.period_start, q.period_end, q.value, q.derived) for q in quarters]


# Apple's fiscal 2023, 53 weeks with a 14-week first quarter; values made up.
FY = date(2022, 9, 25)
Q1_2023, H1_2023, M9_2023, FY_2023 = (
    (FY, date(2022, 12, 31)),  # 98 days
    (FY, date(2023, 4, 1)),  # 189
    (FY, date(2023, 7, 1)),  # 280
    (FY, date(2023, 9, 30)),  # 371
)


def test_a_quarter_is_derived_from_two_year_to_date_totals() -> None:
    # A metric reported only year to date, as operating cash flow is in 10-Qs.
    cash = METRICS["operating_cash_flow"]
    concept = cash.concepts[0]
    rows = [
        fact(concept, Q1_2023, 34e9, "Q1", utc(2023, 2, 2)),
        fact(concept, H1_2023, 62e9, "Q2", utc(2023, 5, 4)),
        fact(concept, M9_2023, 88e9, "Q3", utc(2023, 8, 3)),
        fact(concept, FY_2023, 110e9, "FY", utc(2023, 11, 2), form="10-K"),
    ]

    found = quarterly_values(rows, cash, cash.concepts)

    assert values(found) == [
        (FY, date(2022, 12, 31), 34e9, False),
        (date(2023, 1, 1), date(2023, 4, 1), 28e9, True),
        (date(2023, 4, 2), date(2023, 7, 1), 26e9, True),
        (date(2023, 7, 2), date(2023, 9, 30), 22e9, True),  # 13 weeks of a 53-week year
    ]
    q4 = found[-1]
    assert (q4.accession_numbers, q4.available_at) == (("FY", "Q3"), utc(2023, 11, 2))


def test_no_quarter_is_derived_without_both_totals() -> None:
    concept = REVENUE.concepts[0]
    rows = [
        fact(concept, Q1_2023, 117e9, "Q1", utc(2023, 2, 2)),
        fact(concept, M9_2023, 290e9, "Q3", utc(2023, 8, 3)),
        fact(concept, FY_2023, 383e9, "FY", utc(2023, 11, 2), form="10-K"),
    ]

    found = quarterly_values(rows, REVENUE, REVENUE.concepts)

    # No six-month total, so neither Q2 nor Q3; Q4 is the year minus nine months.
    assert [q.period_end for q in found] == [date(2022, 12, 31), date(2023, 9, 30)]
    assert (found[-1].value, found[-1].derived) == (93e9, True)


def test_a_reported_quarter_beats_a_derived_one() -> None:
    # The 10-K reported the fourth quarter; the full year was re-reported a year later.
    concept = REVENUE.concepts[0]
    q4 = (date(2023, 7, 2), date(2023, 9, 30))
    rows = [
        fact(concept, M9_2023, 290e9, "Q3", utc(2023, 8, 3)),
        fact(concept, FY_2023, 383e9, "FY", utc(2023, 11, 2), form="10-K"),
        fact(concept, q4, 93e9, "FY", utc(2023, 11, 2), form="10-K"),
        fact(concept, FY_2023, 383e9, "FY-next", utc(2024, 11, 1), form="10-K"),
    ]

    [found] = quarterly_values(rows, REVENUE, REVENUE.concepts)

    assert (found.value, found.derived, found.accession_numbers) == (
        93e9,
        False,
        ("FY",),
    )


def test_per_share_amounts_are_never_derived() -> None:
    eps = METRICS["eps_diluted"]
    concept = eps.concepts[0]
    rows = [
        fact(concept, M9_2023, 4.50, "Q3", utc(2023, 8, 3), unit="USD/shares"),
        fact(
            concept,
            FY_2023,
            6.13,
            "FY",
            utc(2023, 11, 2),
            form="10-K",
            unit="USD/shares",
        ),
    ]

    assert quarterly_values(rows, eps, eps.concepts) == []


def test_concepts_are_tried_in_order_for_each_quarter() -> None:
    # The 10-Qs used the old tag; the 10-K, the new one, so only it gives Q4.
    new, old = REVENUE.concepts[0], SALES
    rows = [
        fact(old, Q1_2023, 117e9, "Q1", utc(2023, 2, 2)),
        fact(old, M9_2023, 290e9, "Q3", utc(2023, 8, 3)),
        fact(new, (FY, date(2022, 12, 31)), 117e9, "FY", utc(2023, 11, 2), form="10-K"),
        fact(new, FY_2023, 383e9, "FY", utc(2023, 11, 2), form="10-K"),
    ]

    found = quarterly_values(rows, REVENUE, REVENUE.concepts)

    # The 10-K's copy of Q1, under the new tag, wins; Q4 can't mix the two tags.
    assert [(q.concept, q.period_end) for q in found] == [(new, date(2022, 12, 31))]


def test_an_instant_metric_has_a_value_per_date() -> None:
    assets = METRICS["total_assets"]
    concept = assets.concepts[0]
    rows = [
        fact(concept, (None, date(2023, 4, 1)), 332e9, "Q2", utc(2023, 5, 4)),
        fact(concept, (None, date(2022, 9, 24)), 352e9, "Q2", utc(2023, 5, 4)),
        # A later filing restates the earlier balance sheet.
        fact(
            concept,
            (None, date(2022, 9, 24)),
            352.8e9,
            "FY",
            utc(2023, 11, 2),
            form="10-K",
        ),
    ]

    found = quarterly_values(rows, assets, assets.concepts)

    assert values(found) == [
        (None, date(2022, 9, 24), 352.8e9, False),
        (None, date(2023, 4, 1), 332e9, False),
    ]


def test_labels_come_from_the_filing_for_the_period() -> None:
    concept = REVENUE.concepts[0]
    first = fact(concept, Q1_2023, 117e9, "Q1", utc(2023, 2, 2)) | {
        "fiscal_year": 2023,
        "fiscal_period": "Q1",
    }
    # The next year's 10-Q repeats it, under its own fiscal year and period.
    repeat = fact(concept, Q1_2023, 117e9, "Q1-next", utc(2024, 2, 1)) | {
        "fiscal_year": 2024,
        "fiscal_period": "Q1",
    }
    later = fact(
        concept,
        (date(2023, 10, 1), date(2023, 12, 30)),
        119e9,
        "Q1-next",
        utc(2024, 2, 1),
    ) | {
        "fiscal_year": 2024,
        "fiscal_period": "Q1",
    }

    found = quarterly_values([repeat, later, first], REVENUE, REVENUE.concepts)

    assert [(q.fiscal_year, q.fiscal_period) for q in found] == [
        (2023, "Q1"),
        (2024, "Q1"),
    ]
    # A quarter only ever repeated has no filing of its own here.
    [alone] = quarterly_values([repeat, later], REVENUE, REVENUE.concepts)[:1]
    assert (alone.fiscal_year, alone.fiscal_period) == (None, None)


def view_at(store: Path, as_of: str) -> PointInTimeView:
    return PointInTimeView(parse_knowledge_time(as_of), store=store)


def known(
    store: Path, as_of: str, ticker: str = "AAPL", quarters: int = 8
) -> list[Fundamental]:
    with view_at(store, as_of) as view:
        return view.get_fundamentals_as_of(ticker, "revenue", quarters)


def test_fact_versions_follow_filing_acceptance(fixture_store: Path) -> None:
    # Apple's revenue for the quarter ended March 28, 2020: $58,313 million in its
    # 10-Q, the 10-K, and the next year's 10-Q (doc/time-model.md, rule 6). On June 5,
    # 2020, only the 10-Q had been accepted.
    june_5 = known(fixture_store, "2020-06-05")

    assert june_5 == [
        Fundamental(
            security_id="apple",
            ticker="AAPL",
            cik=320193,
            metric="revenue",
            concept=NEW_REVENUE,
            unit="USD",
            period_start=date(2019, 9, 29),
            period_end=date(2019, 12, 28),
            fiscal_year=2020,
            fiscal_period="Q1",
            value=91819e6,
            derived=False,
            accession_numbers=("0000320193-20-000010",),
            available_at=utc(2020, 1, 28, 23, 2, 44),
            time_assumed=False,
            source="edgar",
            source_ref="0000320193-20-000010",
        ),
        Fundamental(
            security_id="apple",
            ticker="AAPL",
            cik=320193,
            metric="revenue",
            concept=NEW_REVENUE,
            unit="USD",
            period_start=date(2019, 12, 29),
            period_end=date(2020, 3, 28),
            fiscal_year=2020,
            fiscal_period="Q2",
            value=58313e6,
            derived=False,
            accession_numbers=("0000320193-20-000052",),
            available_at=utc(2020, 4, 30, 22, 3, 10),
            time_assumed=False,
            source="edgar",
            source_ref="0000320193-20-000052",
        ),
    ]

    def q2_2020(as_of: str) -> tuple[tuple[str, ...], float]:
        [quarter] = [
            q for q in known(fixture_store, as_of) if q.period_end == date(2020, 3, 28)
        ]
        return quarter.accession_numbers, quarter.value

    # Later, the same number comes from the latest filing that reported it.
    assert q2_2020("2020-11-02") == (("0000320193-20-000096",), 58313e6)
    assert q2_2020("2021-05-03") == (("0000320193-21-000056",), 58313e6)


def test_apples_fourth_quarter_is_the_full_year_minus_nine_months(
    fixture_store: Path,
) -> None:
    # Apple's fiscal 2021 10-K, accepted at 18:04:28 ET on October 28, 2021, didn't
    # report its fourth quarter: it's $365,817 million minus $282,457 million.
    before = known(fixture_store, "2021-10-28T18:00")
    after = known(fixture_store, "2021-11-01", quarters=2)

    assert (before[-1].fiscal_period, before[-1].value) == ("Q3", 81434e6)
    q3, q4 = after
    assert (q3.period_end, q3.value, q3.derived) == (date(2021, 6, 26), 81434e6, False)
    assert q4 == Fundamental(
        security_id="apple",
        ticker="AAPL",
        cik=320193,
        metric="revenue",
        concept=NEW_REVENUE,
        unit="USD",
        period_start=date(2021, 6, 27),
        period_end=date(2021, 9, 25),
        fiscal_year=2021,
        fiscal_period="Q4",
        value=83360e6,
        derived=True,
        accession_numbers=("0000320193-21-000105", "0000320193-21-000065"),
        available_at=utc(2021, 10, 28, 22, 4, 28),
        time_assumed=False,
        source="edgar",
        source_ref="0000320193-21-000105 minus 0000320193-21-000065",
    )


def test_restatement_applies_from_amendment(fixture_store: Path) -> None:
    # A made-up 10-K/A, accepted at 16:30 ET on December 15, 2021, restates Apple's
    # fiscal 2021 revenue to $365,000 million, so the derived fourth quarter changes
    # from its acceptance on, never before.
    before = known(fixture_store, "2021-12-15T16:29")[-1]
    after = known(fixture_store, "2021-12-15T16:30")[-1]

    assert (before.value, before.accession_numbers[0]) == (
        83360e6,
        "0000320193-21-000105",
    )
    assert (after.value, after.accession_numbers, after.available_at) == (
        82543e6,
        ("0000320193-21-900001", "0000320193-21-000065"),
        utc(2021, 12, 15, 21, 30),
    )


def test_microsofts_fiscal_year_ends_in_june(fixture_store: Path) -> None:
    # Fiscal 2021 ran from July 2020 to June 2021. Its 10-K, accepted at 16:21:55 ET on
    # July 29, 2021, gives the fourth quarter: $168,088 million minus $121,936 million.
    def quarters(as_of: str) -> list[tuple[object, ...]]:
        return [
            (
                q.period_start,
                q.period_end,
                q.fiscal_year,
                q.fiscal_period,
                q.value,
                q.derived,
            )
            for q in known(fixture_store, as_of, "MSFT", quarters=4)
        ]

    assert quarters("2021-08-02") == [
        (date(2020, 7, 1), date(2020, 9, 30), 2021, "Q1", 37154e6, False),
        (date(2020, 10, 1), date(2020, 12, 31), 2021, "Q2", 43076e6, False),
        (date(2021, 1, 1), date(2021, 3, 31), 2021, "Q3", 41706e6, False),
        (date(2021, 4, 1), date(2021, 6, 30), 2021, "Q4", 46152e6, True),
    ]
    assert quarters("2021-07-29T16:00")[-1][3] == "Q3"


def test_the_last_quarters_and_bad_requests(fixture_store: Path) -> None:
    assert [
        q.fiscal_period for q in known(fixture_store, "2021-11-01", quarters=1)
    ] == ["Q4"]
    assert known(fixture_store, "2020-06-05", "SPY") == []  # a fund files none
    assert known(fixture_store, "2020-01-02") == []  # before the first 10-Q here
    with view_at(fixture_store, "2020-06-05") as view:
        with pytest.raises(ValueError, match="at least 1"):
            view.get_fundamentals_as_of("AAPL", "revenue", 0)
        with pytest.raises(ValueError, match="unknown metric"):
            view.get_fundamentals_as_of("AAPL", "ebitda")
    # Facebook's shares began trading on May 18, 2012.
    with (
        view_at(fixture_store, "2012-05-17") as view,
        pytest.raises(NotFoundError, match="unknown ticker: FB"),
    ):
        view.get_fundamentals_as_of("FB", "revenue")


def test_a_future_fact_never_reaches_a_read(fixture_store: Path) -> None:
    # The fixture's canary quarter becomes known only in 2099.
    latest = known(fixture_store, "2098-12-31")[-1]

    assert latest.period_end == date(2021, 9, 25)


def test_reads_are_in_the_access_log(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-06-05") as view:
        view.get_fundamentals_as_of("AAPL", "revenue")

        facts = [r for r in view.access_log if r.table == "xbrl_facts"]
    assert {r.source_ref for r in facts} == {
        "0000320193-20-000010",
        "0000320193-20-000052",
    }
