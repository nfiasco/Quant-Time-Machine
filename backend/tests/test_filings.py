from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.data.errors import NotFoundError
from app.data.records import Filing
from app.data.sources import securities
from app.data.store import write_rows
from app.data.tables import FILINGS, SECURITIES
from app.data.timeutil import parse_knowledge_time
from app.data.view import PointInTimeView

# The fixture filings are real Apple and Facebook rows from EDGAR, plus one made-up
# 10-Q/A (tests/fixtures/filings.csv).
Q1_2020 = "0000320193-20-000010"  # quarter ended 2019-12-28, accepted 2020-01-28
Q2_2020 = "0000320193-20-000052"  # quarter ended 2020-03-28, accepted 2020-04-30
Q2_AMENDED = "0000320193-20-900001"  # made up: amends Q2_2020, accepted 2020-06-10
Q3_2020 = "0000320193-20-000062"  # quarter ended 2020-06-27, accepted 2020-07-30
FY_2020 = "0000320193-20-000096"  # 10-K, accepted 2020-10-29
EARNINGS = "0000320193-20-000050"  # 8-K, accepted 2020-04-30 at 16:30 ET
FY_2001 = "0000912057-01-544436"  # 10-K405, with only a filing date


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def view_at(store: Path, as_of: str) -> PointInTimeView:
    """A view of the store at an `as_of`-style time (New York time)."""
    return PointInTimeView(parse_knowledge_time(as_of), store=store)


def latest(store: Path, as_of: str, ticker: str = "AAPL") -> str | None:
    """The accession number of the latest 10-Q known at `as_of`, if any."""
    with view_at(store, as_of) as view:
        filing = view.get_latest_filing_as_of(ticker, "10-Q")
    return None if filing is None else filing.accession_number


def listed(
    store: Path,
    as_of: str,
    ticker: str = "AAPL",
    *,
    forms: Sequence[str] = ("10-K", "10-Q", "8-K"),
    include_amendments: bool = False,
    limit: int = 100,
) -> list[str]:
    """The accession numbers `list_filings_as_of` gives at `as_of`."""
    with view_at(store, as_of) as view:
        filings = view.list_filings_as_of(ticker, forms, include_amendments, limit)
    return [f.accession_number for f in filings]


def test_filing_known_from_acceptance_time(fixture_store: Path) -> None:
    # At 09:30 ET on June 5, 2020: the fiscal Q2 10-Q is public, and fiscal Q3's
    # isn't accepted until July 30.
    with view_at(fixture_store, "2020-06-05") as view:
        filing = view.get_latest_filing_as_of("AAPL")
        ten_qs = [f.accession_number for f in view.list_filings_as_of("AAPL", "10-Q")]

    folder = "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052"
    assert filing == Filing(
        security_id="apple",
        ticker="AAPL",
        cik=320193,
        company_name="Apple Inc.",
        accession_number=Q2_2020,
        form="10-Q",
        is_amendment=False,
        amends=None,
        period_of_report=date(2020, 3, 28),
        filing_date=date(2020, 5, 1),
        available_at=utc(2020, 4, 30, 22, 3, 10),
        time_assumed=False,
        document_url=f"{folder}/a10-qq220203282020.htm",
        index_url=f"{folder}/{Q2_2020}-index.htm",
        source="edgar",
        source_ref=Q2_2020,
    )
    assert Q3_2020 not in ten_qs


def test_filing_visible_after_acceptance_not_filing_date(fixture_store: Path) -> None:
    # Accepted at 18:03 ET on April 30, 2020, after the 5:30 PM cutoff, so its filing
    # date is May 1; it's public from the acceptance.
    assert latest(fixture_store, "2020-04-30T18:05") == Q2_2020
    assert latest(fixture_store, "2020-04-30T18:00") == Q1_2020


def test_amendments_count_only_when_asked_for(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-06-11") as view:
        original = view.get_latest_filing_as_of("AAPL", "10-Q")
        amended = view.get_latest_filing_as_of("AAPL", "10-Q", include_amendments=True)

    assert original is not None
    assert original.accession_number == Q2_2020
    assert amended is not None
    assert (amended.accession_number, amended.form) == (Q2_AMENDED, "10-Q/A")
    assert (amended.is_amendment, amended.amends) == (True, Q2_2020)


def test_the_history_is_newest_first(fixture_store: Path) -> None:
    everything = [FY_2020, Q3_2020, Q2_2020, EARNINGS, Q1_2020, FY_2001]

    assert listed(fixture_store, "2020-12-01") == everything
    assert listed(fixture_store, "2020-12-01", limit=2) == everything[:2]
    assert listed(fixture_store, "2020-12-01", forms=["8-K"]) == [EARNINGS]
    assert listed(fixture_store, "2020-12-01", include_amendments=True) == [
        FY_2020,
        Q3_2020,
        Q2_AMENDED,
        Q2_2020,
        EARNINGS,
        Q1_2020,
        FY_2001,
    ]


def test_a_10k405_counts_as_a_10k(fixture_store: Path) -> None:
    # Apple's 2001 annual report was a 10-K405, and EDGAR has only its date.
    with view_at(fixture_store, "2005-01-03") as view:
        filing = view.get_latest_filing_as_of("AAPL", "10-K")

    assert filing is not None
    assert (filing.accession_number, filing.form) == (FY_2001, "10-K405")
    assert filing.available_at == utc(2001, 12, 22, 4, 59, 59, 999999)
    assert filing.time_assumed is True
    assert filing.company_name == "Apple Computer, Inc."  # the name in 2005


def test_a_fund_that_files_no_reports_has_none(fixture_store: Path) -> None:
    assert latest(fixture_store, "2020-06-05", "SPY") is None
    assert listed(fixture_store, "2020-06-05", "SPY") == []


def test_facebook_had_no_10q_right_after_its_ipo(fixture_store: Path) -> None:
    # Facebook listed on May 18, 2012, and filed its first 10-Q on July 31.
    assert latest(fixture_store, "2012-05-21", "FB") is None
    with view_at(fixture_store, "2012-08-01") as view:
        filing = view.get_latest_filing_as_of("FB")

    assert filing is not None
    assert filing.accession_number == "0001193125-12-325997"
    assert (filing.ticker, filing.company_name) == ("FB", "Facebook, Inc.")


def test_a_future_row_never_reaches_a_read(fixture_store: Path) -> None:
    # The fixture's canary 10-Q is accepted in 2099.
    assert "0000000000-99-000001" not in listed(fixture_store, "2098-12-31")


def test_bad_requests_are_refused(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-06-05") as view:
        with pytest.raises(NotFoundError, match="unknown ticker: NOPE"):
            view.get_latest_filing_as_of("NOPE")
        with pytest.raises(ValueError, match="unknown form 'S-1'"):
            view.list_filings_as_of("AAPL", ["S-1"])
        with pytest.raises(ValueError, match="at least 1"):
            view.list_filings_as_of("AAPL", limit=0)


def test_forms_match_in_any_case(fixture_store: Path) -> None:
    assert listed(fixture_store, "2020-06-05", forms="10-q") == [Q2_2020, Q1_2020]


def test_every_cik_the_security_had_is_searched(store_dir: Path) -> None:
    # Alphabet replaced Google Inc. as the filer on 2015-10-02, under the same tickers.
    write_rows(store_dir, SECURITIES, securities.curated_rows(securities.CURATED))

    def made_up_10q(cik: int, accession: str, accepted: datetime) -> dict[str, object]:
        return {
            "cik": cik,
            "accession_number": accession,
            "form": "10-Q",
            "filing_date": accepted.date(),
            "period_of_report": None,
            "is_amendment": False,
            "amends": None,
            "primary_document": None,
            "items": None,
            "acceptance_raw": None,
            "source": "edgar",
            "source_ref": f"made up: {accession}",
            "available_at": accepted,
            "time_assumed": False,
        }

    write_rows(
        store_dir,
        FILINGS,
        [
            made_up_10q(1288776, "GOOGLE-Q2", utc(2015, 7, 23, 20)),
            made_up_10q(1652044, "ALPHABET-Q3", utc(2015, 10, 29, 20)),
        ],
    )

    assert listed(store_dir, "2015-09-01", "GOOGL") == ["GOOGLE-Q2"]
    with view_at(store_dir, "2015-11-02") as view:
        filings = view.list_filings_as_of("GOOGL")
    assert [(f.accession_number, f.cik) for f in filings] == [
        ("ALPHABET-Q3", 1652044),
        ("GOOGLE-Q2", 1288776),
    ]
    assert {f.company_name for f in filings} == {"Alphabet Inc."}  # the name then


def test_reads_are_in_the_access_log(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-06-05") as view:
        view.get_latest_filing_as_of("AAPL")

        tables = [record.table for record in view.access_log]
        assert tables[-1] == "filings"
        assert view.access_log[-1].key == (320193, Q2_2020)
        assert set(tables[:-1]) == {"securities"}
