from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.prices import RESTRICTED_MESSAGE
from tests.fixture_loader import FIXTURE_DATA_VERSION

# The prices in tests/fixtures/price_bars.csv are made up (Tiingo's terms, D2).


def price(client: TestClient, ticker: str = "AAPL", **params: str) -> Any:
    response = client.get(f"/v1/prices/{ticker}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_bar_known_only_after_close(client: TestClient) -> None:
    assert price(client, as_of="2020-06-05") == {
        "knowledge_time": "2020-06-05T09:30:00-04:00",
        "data_version": FIXTURE_DATA_VERSION,
        "data": {
            "ticker": "AAPL",
            "cik": 320193,
            "session_date": "2020-06-04",
            "open": 102.5,
            "high": 103.5,
            "low": 101.5,
            "close": 102.0,
            "volume": 1300000,
            "available_at": "2020-06-04T16:00:00-04:00",
            "time_assumed": False,
            "source": "tiingo",
            "source_ref": "made up: AAPL 2020-06-04",
        },
        "reason": None,
    }
    # June 5's bar is known at its close, 16:00 ET, and not a minute before.
    assert price(client, as_of="2020-06-05T15:59")["data"]["session_date"] == (
        "2020-06-04"
    )
    assert price(client, as_of="2020-06-05T16:00")["data"]["session_date"] == (
        "2020-06-05"
    )


def test_an_early_close_bar_is_known_at_1300(client: TestClient) -> None:
    data = price(client, as_of="2020-11-27T13:00")["data"]

    assert (data["session_date"], data["available_at"]) == (
        "2020-11-27",
        "2020-11-27T13:00:00-05:00",
    )


def test_tickers_match_in_any_case(client: TestClient) -> None:
    assert price(client, "aapl", as_of="2020-06-05")["data"]["ticker"] == "AAPL"


def test_fb_in_2020_reads_facebooks_bars(client: TestClient) -> None:
    data = price(client, "FB", as_of="2020-06-05")["data"]

    assert (data["ticker"], data["cik"], data["close"]) == ("FB", 1326801, 231.0)


def test_meta_in_2020_is_404(client: TestClient) -> None:
    # Facebook traded as FB until June 9, 2022.
    response = client.get("/v1/prices/META", params={"as_of": "2020-06-05"})

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "unknown_ticker",
        "message": (
            "No security in our data used the ticker META as of June 5, 2020, "
            "9:30 AM ET."
        ),
        "details": [],
    }


@pytest.mark.parametrize(
    ("ticker", "as_of"), [("AAPL", "2020-06-01"), ("SPY", "2020-06-05")]
)
def test_no_bar_yet_is_null_with_a_reason(
    client: TestClient, ticker: str, as_of: str
) -> None:
    body = price(client, ticker, as_of=as_of)

    assert body["data"] is None
    assert body["reason"].startswith(f"Our data has no daily bar for {ticker} from")


def test_the_reason_names_the_moment(client: TestClient) -> None:
    assert price(client, as_of="2020-06-01")["reason"] == (
        "Our data has no daily bar for AAPL from a session that had closed by "
        "June 1, 2020, 9:30 AM ET."
    )


def test_a_future_row_never_reaches_a_response(client: TestClient) -> None:
    # The canary bar, at 999.0, becomes known only in 2099.
    data = price(client, as_of="2098-12-31")["data"]

    assert (data["session_date"], data["close"]) == ("2020-11-27", 121.0)


@pytest.mark.parametrize(
    "params", [{"as_of": "2020-06-05"}, {}, {"as_of": "yesterday"}]
)
def test_prices_are_off_unless_turned_on(
    restricted_client: TestClient, params: dict[str, str]
) -> None:
    # The restriction answers first, so even a request with a bad as_of gets it.
    response = restricted_client.get("/v1/prices/AAPL", params=params)

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "prices_restricted",
            "message": RESTRICTED_MESSAGE,
            "details": [],
        }
    }
