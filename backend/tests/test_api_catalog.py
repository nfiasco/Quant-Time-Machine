import json
from pathlib import Path
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient

from app.backtest.spec import SignalSpec
from app.data.sources.alfred import SERIES

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2] / "doc" / "experiment-spec-v1.schema.json"
)


def catalog(client: TestClient, what: str, **params: str) -> Any:
    response = client.get(f"/v1/catalog/{what}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def coverage(client: TestClient, as_of: str, series_id: str) -> dict[str, Any]:
    """One series' entry in the series catalog."""
    [entry] = [
        entry
        for entry in catalog(client, "series", as_of=as_of)["data"]
        if entry["series_id"] == series_id
    ]
    return entry


def members(client: TestClient, as_of: str) -> dict[str | None, dict[str, Any]]:
    """The companies catalog, by ticker."""
    return {
        company["ticker"]: company
        for company in catalog(client, "companies", as_of=as_of)["data"]
    }


def test_every_catalog_series_is_listed_in_its_order(client: TestClient) -> None:
    data = catalog(client, "series", as_of="2020-06-05")["data"]

    assert [entry["series_id"] for entry in data] == list(SERIES)


def test_series_coverage_is_what_was_published_by_then(client: TestClient) -> None:
    # Half an hour before May 2020's jobs report, April's first print is the latest.
    unrate = coverage(client, "2020-06-05T08:00", "UNRATE")

    assert (unrate["observations"], unrate["vintages"]) == (
        {"first": "1990-01-01", "last": "2020-04-01"},
        {"first": "1990-02-02", "last": "2020-05-08"},
    )


@pytest.mark.parametrize(
    ("as_of", "published"),
    [
        ("2020-06-01T16:14", False),
        ("2020-06-01T16:15", True),  # H.15 comes out at 16:15 ET
    ],
)
def test_a_series_is_covered_from_its_first_release(
    client: TestClient, as_of: str, published: bool
) -> None:
    fedfunds = coverage(client, as_of, "FEDFUNDS")

    assert (fedfunds["observations"] is not None) == published
    assert (fedfunds["vintages"] is not None) == published


def test_series_coverage_never_reaches_a_future_row(client: TestClient) -> None:
    # The canary version of January 1990 is published in 2099.
    unrate = coverage(client, "2098-12-31", "UNRATE")

    assert (unrate["observations"], unrate["vintages"]) == (
        {"first": "1990-01-01", "last": "2025-10-01"},
        {"first": "1990-02-02", "last": "2025-12-16"},
    )


@pytest.mark.parametrize(
    ("as_of", "tickers"),
    [
        ("2020-06-05", ["AAPL", "FB", "TWTR"]),
        # Tesla joined the S&P 500 on December 21, 2020.
        ("2020-12-18", ["AAPL", "FB", "TWTR"]),
        ("2020-12-21", ["AAPL", "FB", "TSLA", "TWTR"]),
        # Facebook became META on June 9, 2022, and Twitter left on November 1, 2022.
        ("2023-01-03", ["AAPL", "META", "TSLA"]),
    ],
)
def test_companies_are_the_members_then_under_their_tickers_then(
    client: TestClient, as_of: str, tickers: list[str]
) -> None:
    data = catalog(client, "companies", as_of=as_of)["data"]

    assert [company["ticker"] for company in data] == tickers


def test_a_member_that_stopped_trading_has_no_ticker(client: TestClient) -> None:
    # Twitter stopped trading on October 28, 2022, but stayed in the index until
    # November 1.
    twitter = members(client, "2022-10-31")[None]

    assert (twitter["name"], twitter["added"]) == ("Twitter, Inc.", "2018-06-07")


def test_company_names_are_those_used_then(client: TestClient) -> None:
    assert members(client, "2020-06-05")["FB"]["name"] == "Facebook, Inc."
    assert members(client, "2023-01-03")["META"]["name"] == "Meta Platforms, Inc."


def test_company_coverage_never_reaches_a_future_row(client: TestClient) -> None:
    # Each fixture table has a canary row for Apple, known only in 2099.
    apple = members(client, "2098-12-31")["AAPL"]

    assert (apple["prices"], apple["filings"], apple["fundamentals"]) == (
        {"first": "2020-06-01", "last": "2020-11-27"},
        {"first": "2001-12-21", "last": "2021-12-15"},
        {"first": "2020-01-28", "last": "2021-12-15"},
    )


def test_no_members_before_2010_is_empty_with_a_reason(client: TestClient) -> None:
    body = catalog(client, "companies", as_of="2009-12-31")

    assert body["data"] == []
    assert body["reason"] == (
        "No company was in a universe as of December 31, 2009, 9:30 AM ET: membership "
        "history starts on 2010-01-01."
    )


def test_the_series_and_companies_catalogs_need_as_of(client: TestClient) -> None:
    for what in ("series", "companies"):
        response = client.get(f"/v1/catalog/{what}")

        assert response.status_code == 422
        assert response.json()["error"]["message"] == "as_of is required."


def test_signals_are_the_specs_signal_types_and_need_no_as_of(
    client: TestClient,
) -> None:
    body = catalog(client, "signals")
    (union, _) = get_args(SignalSpec)

    assert set(body) == {"spec_version", "data"}
    assert body["spec_version"] == 1
    assert [signal["type"] for signal in body["data"]] == [
        get_args(model.model_fields["type"].annotation)[0] for model in get_args(union)
    ]


def test_signal_schemas_are_the_committed_json_schemas(client: TestClient) -> None:
    committed = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))["$defs"]

    for signal in catalog(client, "signals")["data"]:
        schema = signal["parameters"]
        assert schema == committed[schema["title"]], signal["type"]
        assert schema["properties"]["type"]["const"] == signal["type"]
        assert signal["description"] == schema["description"]
