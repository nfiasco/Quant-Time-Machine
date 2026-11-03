from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.data.sources.alfred import SERIES


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
