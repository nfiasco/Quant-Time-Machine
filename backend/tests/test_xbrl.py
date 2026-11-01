from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.config import get_settings
from app.data.http import client_for
from app.data.sources.xbrl import END_OF_DAY, fact_rows, fetch_company_facts
from app.data.store import write_rows
from app.data.tables import XBRL_FACTS
from app.data.timeutil import market_time
from app.data.view import PointInTimeView

REVENUE = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
SHARES = "dei:EntityCommonStockSharesOutstanding"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def accepted(when: datetime, *, assumed: bool = False) -> dict[str, Any]:
    """The part of a `filings` row that the facts it reported take on."""
    return {"available_at": when, "time_assumed": assumed}


# Apple's 10-Q for fiscal Q2 2020, its 10-K for fiscal 2020, and its 10-Q for fiscal Q2
# 2021, with their acceptance times (doc/time-model.md, rule 6).
APPLE_FILINGS = {
    "0000320193-20-000052": accepted(utc(2020, 4, 30, 22, 3, 10)),
    "0000320193-20-000096": accepted(utc(2020, 10, 29, 22, 6, 25)),
    "0000320193-21-000056": accepted(utc(2021, 4, 28, 22, 2, 54)),
}


def copy_in(accn: str, fy: int, fp: str, form: str, filed: str) -> dict[str, Any]:
    """Apple's revenue for the quarter ended March 28, 2020, as one filing reported it,
    in SEC's company facts."""
    return {
        "start": "2019-12-29",
        "end": "2020-03-28",
        "val": 58313000000,
        "accn": accn,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }


# The value in each filing that reported it. SEC's frame marks the last one.
Q2_2020 = [
    copy_in("0000320193-20-000052", 2020, "Q2", "10-Q", "2020-05-01"),
    copy_in("0000320193-20-000096", 2020, "FY", "10-K", "2020-10-30"),
    copy_in("0000320193-21-000056", 2021, "Q2", "10-Q", "2021-04-29")
    | {"frame": "CY2020Q1"},
]

# The cover of the same 10-Q: shares outstanding on April 17, 2020.
COVER = {
    "end": "2020-04-17",
    "val": 4334335000,
    "accn": "0000320193-20-000052",
    "fy": 2020,
    "fp": "Q2",
    "form": "10-Q",
    "filed": "2020-05-01",
}


def company_facts(
    concepts: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    """SEC's company facts, with `concepts` mapping "taxonomy:Name" to each unit's
    facts."""
    facts: dict[str, dict[str, Any]] = {}
    for concept, units in concepts.items():
        taxonomy, name = concept.split(":")
        facts.setdefault(taxonomy, {})[name] = {"label": name, "units": units}
    return {"cik": 320193, "entityName": "Apple Inc.", "facts": facts}


def test_fact_versions_follow_filing_acceptance(store_dir: Path) -> None:
    # The data side of the golden test: each filing's copy of the value is a row of
    # its own, known from that filing's acceptance time, so June 5, 2020 sees only the
    # 10-Q's.
    rows = fact_rows(320193, company_facts({REVENUE: {"USD": Q2_2020}}), APPLE_FILINGS)
    write_rows(store_dir, XBRL_FACTS, rows)

    with PointInTimeView(utc(2020, 6, 5, 13, 30), store=store_dir) as view:
        known = view._select("xbrl_facts")

    assert [(r["accession_number"], r["available_at"]) for r in rows] == [
        ("0000320193-20-000052", utc(2020, 4, 30, 22, 3, 10)),
        ("0000320193-20-000096", utc(2020, 10, 29, 22, 6, 25)),
        ("0000320193-21-000056", utc(2021, 4, 28, 22, 2, 54)),
    ]
    assert [(r["accession_number"], r["value"]) for r in known] == [
        ("0000320193-20-000052", 58313000000.0)
    ]


def test_a_row_is_the_fact_as_its_filing_reported_it() -> None:
    facts = company_facts({REVENUE: {"USD": Q2_2020[:1]}})

    [row] = fact_rows(320193, facts, APPLE_FILINGS)

    assert row == {
        "cik": 320193,
        "accession_number": "0000320193-20-000052",
        "concept": REVENUE,
        "unit": "USD",
        "period_start": date(2019, 12, 29),
        "period_end": date(2020, 3, 28),
        "duration_days": 91,  # 13 weeks
        "value": 58313000000.0,
        "fiscal_year": 2020,
        "fiscal_period": "Q2",
        "form": "10-Q",
        "filed": date(2020, 5, 1),
        "source": "edgar",
        "source_ref": "0000320193-20-000052",
        "available_at": utc(2020, 4, 30, 22, 3, 10),
        "time_assumed": False,
    }


def test_secs_frame_is_never_stored() -> None:
    # SEC puts it on the last-filed fact for each period, which no one knew at the time.
    rows = fact_rows(320193, company_facts({REVENUE: {"USD": Q2_2020}}), APPLE_FILINGS)

    assert "frame" not in XBRL_FACTS.all_columns
    assert all("frame" not in row for row in rows)


def test_an_instant_has_no_start_and_no_days() -> None:
    [row] = fact_rows(
        320193, company_facts({SHARES: {"shares": [COVER]}}), APPLE_FILINGS
    )

    assert (row["period_start"], row["period_end"], row["duration_days"]) == (
        None,
        date(2020, 4, 17),
        0,
    )


def test_a_fact_outside_filings_counts_from_the_end_of_its_filed_date() -> None:
    # Microsoft's proxy statement of 2026-10-21 repeats fiscal 2022's net income in its
    # pay-versus-performance table. Proxies aren't in `filings`, so the fact counts as
    # known at the end of its filed date in New York, flagged (rule 11).
    proxy = {
        "start": "2021-07-01",
        "end": "2022-06-30",
        "val": 72738000000,
        "accn": "0001193125-26-427849",
        "fy": None,
        "fp": None,
        "form": "DEF 14A",
        "filed": "2026-10-21",
        "frame": "CY2022",
    }
    facts = company_facts({"us-gaap:NetIncomeLoss": {"USD": [proxy]}})

    [row] = fact_rows(789019, facts, {})

    assert (row["available_at"], row["time_assumed"]) == (
        utc(2026, 10, 22, 3, 59, 59, 999999),
        True,
    )
    assert (row["fiscal_year"], row["fiscal_period"], row["form"]) == (
        None,
        None,
        "DEF 14A",
    )


def test_a_fact_takes_on_its_filings_assumed_time() -> None:
    end_of_day = utc(2020, 5, 2, 3, 59, 59, 999999)
    filings = {"0000320193-20-000052": accepted(end_of_day, assumed=True)}

    [row] = fact_rows(320193, company_facts({REVENUE: {"USD": Q2_2020[:1]}}), filings)

    assert (row["available_at"], row["time_assumed"]) == (end_of_day, True)


def test_only_curated_concepts_are_kept_in_every_unit() -> None:
    facts = company_facts(
        {
            REVENUE: {"USD": Q2_2020[:1], "EUR": [Q2_2020[0] | {"val": 1}]},
            "us-gaap:GrossProfit": {"USD": [Q2_2020[0] | {"val": 22370000000}]},
            SHARES: {"shares": [COVER]},
            "dei:EntityPublicFloat": {"USD": [COVER | {"val": 1}]},
        }
    )

    rows = fact_rows(320193, facts, APPLE_FILINGS)

    assert sorted((r["concept"], r["unit"]) for r in rows) == [
        (SHARES, "shares"),
        (REVENUE, "EUR"),
        (REVENUE, "USD"),
    ]


def test_only_exact_duplicates_are_dropped(store_dir: Path) -> None:
    # The same fact twice, once with SEC's frame, is an exact duplicate once the frame
    # is gone. Another value from the same filing and period isn't, so both stay.
    original = Q2_2020[0]
    facts = company_facts(
        {
            REVENUE: {
                "USD": [
                    original,
                    original | {"frame": "CY2020Q1"},
                    original | {"val": 58000000000},
                ]
            }
        }
    )

    result = write_rows(store_dir, XBRL_FACTS, fact_rows(320193, facts, APPLE_FILINGS))

    with PointInTimeView(utc(2026, 1, 1), store=store_dir) as view:
        values = [row["value"] for row in view._select("xbrl_facts")]
    assert result.written == 2
    assert sorted(values) == [58000000000.0, 58313000000.0]


def test_fixture_facts_are_known_when_their_filings_were_accepted(
    fixture_store: Path,
) -> None:
    # As ingestion would have written them (tests/fixtures/README.md).
    with PointInTimeView(utc(2098, 12, 31), store=fixture_store) as view:
        filings = {row["accession_number"]: row for row in view._select("filings")}
        facts = view._select("xbrl_facts")

    assert facts
    for fact in facts:
        filing = filings.get(fact["accession_number"])
        expected = (
            (market_time(fact["filed"], END_OF_DAY), True)
            if filing is None
            else (filing["available_at"], filing["time_assumed"])
        )
        assert (fact["available_at"], fact["time_assumed"]) == expected, fact


@pytest.mark.network
def test_live_company_facts_hold_each_filings_copy(tmp_path: Path) -> None:
    # One request to SEC: Apple's revenue for the quarter ended March 28, 2020, as each
    # of the three filings that reported it.
    live = get_settings()
    if live.sec_user_agent is None:
        pytest.skip("SEC_USER_AGENT isn't set in backend/.env")

    with client_for("sec", live.model_copy(update={"data_dir": tmp_path})) as client:
        rows = fact_rows(320193, fetch_company_facts(client, 320193), APPLE_FILINGS)

    copies = {
        (row["accession_number"], row["value"], row["available_at"])
        for row in rows
        if row["concept"] == REVENUE
        and row["period_end"] == date(2020, 3, 28)
        and row["duration_days"] == 91
    }
    assert copies == {
        (accession, 58313000000.0, filing["available_at"])
        for accession, filing in APPLE_FILINGS.items()
    }
