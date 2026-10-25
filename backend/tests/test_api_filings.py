from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient

from app.api.filings import FormFamily
from app.data.sources.edgar import FORM_FAMILIES

# Apple's 10-Qs for the quarters ended December 28, 2019, March 28, 2020, and June 27,
# 2020, accepted on January 28, April 30, and July 30 (doc/time-model.md, rule 5).
Q1, Q2, Q3 = (
    "0000320193-20-000010",
    "0000320193-20-000052",
    "0000320193-20-000062",
)
EARNINGS_8K = "0000320193-20-000050"
FY2020_10K = "0000320193-20-000096"
FY2001_10K405 = "0000912057-01-544436"
AMENDED_Q2 = "0000320193-20-900001"  # made up, for the amendment tests


def latest(client: TestClient, ticker: str = "AAPL", **params: str) -> Any:
    response = client.get(f"/v1/filings/{ticker}/latest", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def listed(client: TestClient, ticker: str = "AAPL", **params: str) -> list[str]:
    response = client.get(f"/v1/filings/{ticker}", params=params)
    assert response.status_code == 200, response.text
    return [filing["accession_number"] for filing in response.json()["data"]]


def test_filing_known_from_acceptance_time(client: TestClient) -> None:
    assert latest(client, as_of="2020-06-05", form="10-Q") == {
        "knowledge_time": "2020-06-05T09:30:00-04:00",
        "data_version": None,
        "data": {
            "ticker": "AAPL",
            "cik": 320193,
            "company_name": "Apple Inc.",
            "accession_number": Q2,
            "form": "10-Q",
            "is_amendment": False,
            "amends": None,
            "period_of_report": "2020-03-28",
            "filing_date": "2020-05-01",
            "available_at": "2020-04-30T18:03:10-04:00",
            "time_assumed": False,
            "document_url": (
                "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/"
                "a10-qq220203282020.htm"
            ),
            "index_url": (
                "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/"
                "0000320193-20-000052-index.htm"
            ),
            "source": "edgar",
            "source_ref": Q2,
        },
        "reason": None,
    }


def test_filing_visible_after_acceptance_not_filing_date(client: TestClient) -> None:
    # Accepted at 18:03:10 ET on April 30; its filing date is May 1.
    assert latest(client, as_of="2020-04-30T18:03")["data"]["accession_number"] == Q1
    assert latest(client, as_of="2020-04-30T18:05")["data"]["accession_number"] == Q2


def test_each_form_family(client: TestClient) -> None:
    earnings = latest(client, as_of="2020-06-05", form="8-K")["data"]
    annual = latest(client, as_of="2020-06-05", form="10-K")["data"]

    assert earnings["available_at"] == "2020-04-30T16:30:41-04:00"
    assert earnings["accession_number"] == EARNINGS_8K
    # A 10-K405 counts as a 10-K. EDGAR kept only its date, so its time is the end of
    # that day, flagged as assumed.
    assert (
        annual["accession_number"],
        annual["form"],
        annual["time_assumed"],
        annual["available_at"],
        annual["company_name"],
    ) == (
        FY2001_10K405,
        "10-K405",
        True,
        "2001-12-21T23:59:59.999999-05:00",
        "Apple Inc.",
    )


def test_amendments_count_only_when_asked_for(client: TestClient) -> None:
    amended = latest(client, as_of="2020-06-11", include_amendments="true")["data"]

    assert latest(client, as_of="2020-06-11")["data"]["accession_number"] == Q2
    assert (
        amended["accession_number"],
        amended["form"],
        amended["is_amendment"],
        amended["amends"],
    ) == (AMENDED_Q2, "10-Q/A", True, Q2)


def test_facebook_had_no_10q_right_after_its_ipo(client: TestClient) -> None:
    first = latest(client, "fb", as_of="2012-08-01")["data"]

    assert latest(client, "FB", as_of="2012-05-21") == {
        "knowledge_time": "2012-05-21T09:30:00-04:00",
        "data_version": None,
        "data": None,
        "reason": (
            "No 10-Q from Facebook, Inc. had been accepted by EDGAR by May 21, 2012, "
            "9:30 AM ET."
        ),
    }
    assert (first["ticker"], first["company_name"], first["available_at"]) == (
        "FB",
        "Facebook, Inc.",
        "2012-07-31T16:39:19-04:00",
    )


def test_fb_before_its_ipo_is_404(client: TestClient) -> None:
    response = client.get("/v1/filings/FB/latest", params={"as_of": "2012-05-17"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_ticker"


def test_a_fund_that_files_no_reports_has_none(client: TestClient) -> None:
    history = client.get("/v1/filings/SPY", params={"as_of": "2020-06-05"}).json()

    assert latest(client, "SPY", as_of="2020-06-05")["reason"] == (
        "No 10-Q from SPDR S&P 500 ETF Trust had been accepted by EDGAR by June 5, "
        "2020, 9:30 AM ET."
    )
    assert history["data"] == []
    assert history["reason"] == (
        "No 10-K, 10-Q, or 8-K filings from SPDR S&P 500 ETF Trust had been accepted "
        "by EDGAR by June 5, 2020, 9:30 AM ET."
    )


def test_the_history_is_newest_first(client: TestClient) -> None:
    everything = [FY2020_10K, Q3, Q2, EARNINGS_8K, Q1, FY2001_10K405]

    assert listed(client, as_of="2020-12-01") == everything
    assert listed(client, as_of="2020-12-01", limit="2") == everything[:2]
    assert listed(client, as_of="2020-12-01", include_amendments="true")[:3] == [
        FY2020_10K,
        Q3,
        AMENDED_Q2,
    ]


def test_june_5_2020_sees_two_10qs_but_not_the_third(client: TestClient) -> None:
    assert listed(client, as_of="2020-06-05", form="10-Q") == [Q2, Q1]
    assert listed(client, as_of="2020-06-05") == [Q2, EARNINGS_8K, Q1, FY2001_10K405]


def test_a_future_row_never_reaches_a_response(client: TestClient) -> None:
    # The canary 10-Q becomes known only in 2099.
    assert latest(client, as_of="2098-12-31")["data"]["accession_number"] == Q3
    assert "0000000000-99-000001" not in listed(client, as_of="2098-12-31")


@pytest.mark.parametrize(
    ("path", "params", "field"),
    [
        ("/v1/filings/AAPL/latest", {"form": "S-1"}, "form"),
        ("/v1/filings/AAPL/latest", {"form": "10-q"}, "form"),
        ("/v1/filings/AAPL", {"limit": "0"}, "limit"),
        ("/v1/filings/AAPL", {"limit": "1001"}, "limit"),
        ("/v1/filings/AAPL", {"limit": "abc"}, "limit"),
        ("/v1/filings/AAPL", {"include_amendments": "maybe"}, "include_amendments"),
    ],
)
def test_bad_parameters_are_422(
    client: TestClient, path: str, params: dict[str, str], field: str
) -> None:
    response = client.get(path, params={"as_of": "2020-06-05", **params})

    assert response.status_code == 422
    [detail] = response.json()["error"]["details"]
    assert detail["field"] == field


def test_form_families_are_the_ones_ingested() -> None:
    assert set(get_args(FormFamily)) == set(FORM_FAMILIES)
