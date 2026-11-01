from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient

from app.api.fundamentals import MetricName
from app.data.sources.metrics import METRICS
from tests.fixture_loader import FIXTURE_DATA_VERSION

REVENUE = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"


def fundamentals(client: TestClient, ticker: str = "AAPL", **params: str) -> Any:
    response = client.get(f"/v1/fundamentals/{ticker}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_fact_versions_follow_filing_acceptance(client: TestClient) -> None:
    # Apple's revenue for the quarter ended March 28, 2020, is in three filings; on
    # June 5, 2020, only the 10-Q had been accepted (doc/time-model.md, rule 6).
    body = fundamentals(client, as_of="2020-06-05", quarters="1")

    assert body == {
        "knowledge_time": "2020-06-05T09:30:00-04:00",
        "data_version": FIXTURE_DATA_VERSION,
        "data": [
            {
                "ticker": "AAPL",
                "cik": 320193,
                "metric": "revenue",
                "concept": REVENUE,
                "unit": "USD",
                "period_start": "2019-12-29",
                "period_end": "2020-03-28",
                "fiscal_year": 2020,
                "fiscal_period": "Q2",
                "value": 58313000000.0,
                "derived": False,
                "accession_numbers": ["0000320193-20-000052"],
                "available_at": "2020-04-30T18:03:10-04:00",
                "time_assumed": False,
                "source": "edgar",
                "source_ref": "0000320193-20-000052",
            }
        ],
        "reason": None,
    }
    later = fundamentals(client, as_of="2021-05-03", quarters="8")["data"]
    [q2_2020] = [q for q in later if q["period_end"] == "2020-03-28"]
    assert q2_2020["accession_numbers"] == ["0000320193-21-000056"]


def test_a_fourth_quarter_is_the_full_year_minus_nine_months(
    client: TestClient,
) -> None:
    [q4] = fundamentals(client, as_of="2021-11-01", quarters="1")["data"]

    assert (q4["fiscal_year"], q4["fiscal_period"], q4["value"], q4["derived"]) == (
        2021,
        "Q4",
        83360000000.0,
        True,
    )
    assert q4["accession_numbers"] == ["0000320193-21-000105", "0000320193-21-000065"]
    assert q4["available_at"] == "2021-10-28T18:04:28-04:00"


def test_restatement_applies_from_amendment(client: TestClient) -> None:
    # A made-up 10-K/A, accepted at 16:30 ET on December 15, 2021, restates fiscal 2021.
    before = fundamentals(client, as_of="2021-12-15T16:29", quarters="1")["data"]
    after = fundamentals(client, as_of="2021-12-15T16:30", quarters="1")["data"]

    assert before[0]["value"] == 83360000000.0
    assert after[0]["value"] == 82543000000.0


def test_microsofts_fiscal_year_ends_in_june(client: TestClient) -> None:
    data = fundamentals(client, "msft", as_of="2021-08-02", quarters="4")["data"]

    assert [
        (q["period_start"], q["period_end"], q["fiscal_period"], q["derived"])
        for q in data
    ] == [
        ("2020-07-01", "2020-09-30", "Q1", False),
        ("2020-10-01", "2020-12-31", "Q2", False),
        ("2021-01-01", "2021-03-31", "Q3", False),
        ("2021-04-01", "2021-06-30", "Q4", True),
    ]
    assert {q["fiscal_year"] for q in data} == {2021}


def test_jpmorgans_revenue_comes_through_its_override(client: TestClient) -> None:
    [quarter] = fundamentals(client, "JPM", as_of="2015-06-01")["data"]

    assert (quarter["concept"], quarter["value"]) == (
        "us-gaap:RevenuesNetOfInterestExpense",
        23215000000.0,
    )


def test_a_fund_reports_none(client: TestClient) -> None:
    body = fundamentals(client, "SPY", as_of="2020-06-05", metric="total_assets")

    assert body["data"] == []
    assert body["reason"] == (
        "No filing EDGAR had accepted from SPDR S&P 500 ETF Trust by June 5, 2020, "
        "9:30 AM ET reported total assets."
    )


def test_fb_before_its_ipo_is_404(client: TestClient) -> None:
    response = client.get("/v1/fundamentals/FB", params={"as_of": "2012-05-17"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_ticker"


def test_a_future_fact_never_reaches_a_response(client: TestClient) -> None:
    # The canary quarter becomes known only in 2099.
    data = fundamentals(client, as_of="2098-12-31")["data"]

    assert data[-1]["period_end"] == "2021-09-25"


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"metric": "ebitda"}, "metric"),
        ({"metric": "Revenue"}, "metric"),
        ({"quarters": "0"}, "quarters"),
        ({"quarters": "41"}, "quarters"),
        ({"quarters": "abc"}, "quarters"),
        ({"as_of": "yesterday"}, "as_of"),
    ],
)
def test_bad_parameters_are_422(
    client: TestClient, params: dict[str, str], field: str
) -> None:
    response = client.get(
        "/v1/fundamentals/AAPL", params={"as_of": "2020-06-05", **params}
    )

    assert response.status_code == 422
    [detail] = response.json()["error"]["details"]
    assert detail["field"] == field


def test_metric_names_are_the_catalogs() -> None:
    assert list(get_args(MetricName)) == list(METRICS)
