from typing import Any

import pytest
from fastapi.testclient import TestClient


def macro(client: TestClient, series_id: str = "UNRATE", **params: str) -> Any:
    response = client.get(f"/v1/macro/{series_id}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_june_5_2020_sees_mays_first_print(client: TestClient) -> None:
    assert macro(client, as_of="2020-06-05") == {
        "knowledge_time": "2020-06-05T09:30:00-04:00",
        "data_version": None,
        "data": {
            "series_id": "UNRATE",
            "title": "Unemployment Rate",
            "units": "Percent",
            "frequency": "Monthly",
            "seasonal_adjustment": "Seasonally Adjusted",
            "release": "Employment Situation",
            "period": "2020-05-01",
            "value": 13.3,
            "vintage_date": "2020-06-05",
            "available_at": "2020-06-05T08:30:00-04:00",
            "time_assumed": False,
            "source": "alfred",
            "source_ref": "UNRATE vintage 2020-06-05",
        },
        "reason": None,
    }


def test_half_an_hour_earlier_the_latest_is_aprils(client: TestClient) -> None:
    data = macro(client, as_of="2020-06-05T08:00")["data"]

    assert (data["period"], data["value"], data["available_at"]) == (
        "2020-04-01",
        14.7,
        "2020-05-08T08:30:00-04:00",
    )


@pytest.mark.parametrize(
    ("as_of", "value", "available_at"),
    [
        ("2020-06-05", 14.7, "2020-05-08T08:30:00-04:00"),
        # Revised in January 2021's release, in winter: -05:00.
        ("2021-06-01", 14.8, "2021-01-08T08:30:00-05:00"),
    ],
)
def test_a_period_reads_its_latest_version_known_then(
    client: TestClient, as_of: str, value: float, available_at: str
) -> None:
    data = macro(client, as_of=as_of, period="2020-04-01")["data"]

    assert (data["value"], data["available_at"]) == (value, available_at)


def test_a_period_not_published_yet_is_null_with_a_reason(client: TestClient) -> None:
    body = macro(client, as_of="2020-06-05", period="2020-06-01")

    assert body["data"] is None
    assert body["reason"] == (
        "No UNRATE value for 2020-06-01 had been published by June 5, 2020, 9:30 AM ET."
    )


def test_a_series_with_nothing_published_yet_is_null_with_a_reason(
    client: TestClient,
) -> None:
    assert macro(client, "PAYEMS", as_of="2020-06-05") == {
        "knowledge_time": "2020-06-05T09:30:00-04:00",
        "data_version": None,
        "data": None,
        "reason": "No PAYEMS value had been published by June 5, 2020, 9:30 AM ET.",
    }


def test_a_value_published_as_missing_is_null_without_a_reason(
    client: TestClient,
) -> None:
    body = macro(client, as_of="2025-12-16T09:30", period="2025-10-01")

    assert body["data"]["value"] is None
    assert body["reason"] is None


def test_series_ids_match_in_any_case(client: TestClient) -> None:
    assert macro(client, "unrate", as_of="2020-06-05")["data"]["series_id"] == "UNRATE"


def test_a_future_row_never_reaches_a_response(client: TestClient) -> None:
    # The canary row, 99.9 for January 1990, becomes known only in 2099.
    data = macro(client, as_of="2098-12-31", period="1990-01-01")["data"]

    assert data["value"] == 5.4


def test_a_series_outside_the_catalog_is_404(client: TestClient) -> None:
    response = client.get("/v1/macro/DGS10", params={"as_of": "2020-06-05"})

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "unknown_series",
        "message": "DGS10 isn't a series in our catalog.",
        "details": [],
    }


@pytest.mark.parametrize(
    "period", ["1585699200", "2020-4-1", "2020-04-01T00:00:00", "2020-02-30"]
)
def test_period_must_be_a_date(client: TestClient, period: str) -> None:
    response = client.get(
        "/v1/macro/UNRATE", params={"as_of": "2020-06-05", "period": period}
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {"field": "period", "message": "period must be a date such as 2020-04-01."}
    ]
