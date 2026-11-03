from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.fixture_loader import FIXTURE_DATA_VERSION

TIME_MODEL = Path(__file__).resolve().parents[2] / "doc" / "time-model.md"
TABLE_HEADING = "\n## June 5, 2020, at 09:30 ET (13:30Z)\n"

JUNE_5 = {"as_of": "2020-06-05", "tickers": "AAPL,TSLA", "series": "UNRATE,FEDFUNDS"}
"""The June 5, 2020 table in doc/time-model.md, as one request."""

T = datetime.fromisoformat("2020-06-05T09:30:00-04:00")


def snapshot(client: TestClient, **params: str) -> Any:
    response = client.get("/v1/snapshot", params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def june_5(restricted_client: TestClient) -> Any:
    """The June 5, 2020 snapshot, from a server with raw prices off, as deployed."""
    return snapshot(restricted_client, **JUNE_5)["data"]


def company(section: Any, ticker: str) -> Any:
    [found] = [entry for entry in section["companies"] if entry["ticker"] == ticker]
    return found


def series(section: Any, series_id: str) -> Any:
    [found] = [entry for entry in section["series"] if entry["series_id"] == series_id]
    return found


def pick(record: Any, *fields: str) -> tuple[Any, ...]:
    return tuple(record[field] for field in fields)


Read = Callable[[Any], Any]

# Each row of the table: the section it must be in, what to read there, and what that
# is. Their ids are the table's own labels, which a test below checks.
ROWS = [
    pytest.param(
        "known",
        lambda s: pick(
            company(s, "AAPL")["latest_bar"], "session_date", "available_at", "close"
        ),
        ("2020-06-04", "2020-06-04T16:00:00-04:00", None),
        id="AAPL daily bars through June 4",
    ),
    pytest.param(
        "not_yet_known",
        lambda s: company(s, "AAPL")["next_bar"],
        {"session_date": "2020-06-05", "available_at": "2020-06-05T16:00:00-04:00"},
        id="AAPL's June 5 bar",
    ),
    pytest.param(
        "known",
        lambda s: pick(
            series(s, "UNRATE")["latest"], "period", "value", "available_at"
        ),
        ("2020-05-01", 13.3, "2020-06-05T08:30:00-04:00"),
        id="May 2020 unemployment rate, first print 13.3%",
    ),
    pytest.param(
        "not_yet_known",
        lambda s: [
            pick(version, "period", "value", "available_at")
            for version in series(s, "UNRATE")["revisions"]
        ],
        [("2020-05-01", 13.2, "2022-01-07T08:30:00-05:00")],
        id="Later revisions to May 2020 (for example, today's 13.2%)",
    ),
    pytest.param(
        "known",
        lambda s: pick(
            company(s, "AAPL")["latest_filings"]["10-Q"],
            "accession_number",
            "period_of_report",
            "available_at",
        ),
        ("0000320193-20-000052", "2020-03-28", "2020-04-30T18:03:10-04:00"),
        id="Apple's 10-Q for the quarter ended March 28, 2020",
    ),
    pytest.param(
        "known",
        lambda s: pick(
            company(s, "AAPL")["latest_revenue"],
            "period_end",
            "value",
            "accession_numbers",
            "available_at",
        ),
        (
            "2020-03-28",
            58313000000.0,
            ["0000320193-20-000052"],
            "2020-04-30T18:03:10-04:00",
        ),
        id="Apple's fiscal Q2 2020 revenue, $58,313 million, from that 10-Q",
    ),
    pytest.param(
        "not_yet_known",
        lambda s: pick(
            company(s, "AAPL")["later_revenue"][0],
            "period_end",
            "value",
            "accession_numbers",
            "available_at",
        ),
        (
            "2020-03-28",
            58313000000.0,
            ["0000320193-20-000096"],
            "2020-10-29T18:06:25-04:00",
        ),
        id="The same revenue as re-reported in the fiscal 2020 10-K",
    ),
    pytest.param(
        "not_yet_known",
        lambda s: pick(
            company(s, "AAPL")["next_filings"]["10-Q"],
            "accession_number",
            "period_of_report",
            "available_at",
        ),
        ("0000320193-20-000062", "2020-06-27", "2020-07-30T19:29:09-04:00"),
        id="Apple's 10-Q for the quarter ended June 27, 2020",
    ),
    pytest.param(
        "not_yet_known",
        lambda s: [
            pick(filing, "accession_number", "form", "amends", "available_at")
            for filing in company(s, "AAPL")["later_amendments"]
        ],
        [
            (
                "0000320193-20-900001",
                "10-Q/A",
                "0000320193-20-000052",
                "2020-06-10T16:00:00-04:00",
            )
        ],
        id="Any 10-Q/A or 10-K/A filed after June 5",
    ),
    pytest.param(
        "known",
        lambda s: pick(
            series(s, "FEDFUNDS")["latest"], "period", "value", "available_at"
        ),
        ("2020-05-01", 0.05, "2020-06-01T16:15:00-04:00"),
        id="Fed and other economic data as published by that morning",
    ),
    pytest.param(
        "not_yet_known",
        lambda s: [
            pick(change, "universe", "change", "effective", "available_at")
            for change in company(s, "TSLA")["universe_changes"]
        ],
        [("starter_large_caps", "joins", "2020-12-21", "2020-12-21T00:00:00-05:00")],
        id="Universe changes effective after June 5",
    ),
]


@pytest.mark.parametrize(("section", "read", "expected"), ROWS)
def test_june_5_2020_table(
    june_5: Any, section: str, read: Read, expected: Any
) -> None:
    assert read(june_5[section]) == expected


def test_every_row_of_the_time_models_table_is_checked() -> None:
    text = TIME_MODEL.read_text(encoding="utf-8")
    table = text.split(TABLE_HEADING, 1)[1].split("\n## ", 1)[0]
    rows = [
        [cell.strip() for cell in line.strip("|").split("|")]
        for line in table.splitlines()
        if line.startswith("| ") and not line.startswith(("| Item ", "| --- "))
    ]

    assert [(label, known) for label, _, known in rows] == [
        (row.id, "✓" if row.values[0] == "known" else "✗") for row in ROWS
    ]


def test_tesla_wasnt_in_the_universe_yet(june_5: Any) -> None:
    assert company(june_5["known"], "TSLA")["universes"] == []
    assert [
        pick(member, "universe", "added")
        for member in company(june_5["known"], "AAPL")["universes"]
    ] == [("starter_large_caps", "2010-01-01")]


def timestamps(node: Any) -> Iterator[datetime]:
    """Every `available_at` in a part of a response."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "available_at":
                yield datetime.fromisoformat(value)
            else:
                yield from timestamps(value)
    elif isinstance(node, list):
        for item in node:
            yield from timestamps(item)


def test_known_came_by_t_and_not_yet_known_after(june_5: Any) -> None:
    known, later = (
        list(timestamps(june_5["known"])),
        list(timestamps(june_5["not_yet_known"])),
    )

    assert known and all(moment <= T for moment in known)
    assert later and all(moment > T for moment in later)


def test_prices_show_only_where_raw_prices_are_on(
    client: TestClient, restricted_client: TestClient
) -> None:
    served = snapshot(client, **JUNE_5)["data"]
    withheld = snapshot(restricted_client, **JUNE_5)["data"]
    prices = ("open", "high", "low", "close", "volume")

    # The made-up June 4 bar in tests/fixtures/price_bars.csv.
    on = company(served["known"], "AAPL")
    assert on["prices_withheld"] is False
    assert pick(on["latest_bar"], *prices) == (102.5, 103.5, 101.5, 102.0, 1300000)
    off = company(withheld["known"], "AAPL")
    assert off["prices_withheld"] is True
    assert pick(off["latest_bar"], *prices) == (None,) * 5
    assert off["latest_bar"]["session_date"] == "2020-06-04"
    # A next bar never carries prices: they weren't known yet.
    for data in (served, withheld):
        next_bar = company(data["not_yet_known"], "AAPL")["next_bar"]
        assert set(next_bar) == {"session_date", "available_at"}


def test_before_the_jobs_report_aprils_print_is_the_latest(client: TestClient) -> None:
    data = snapshot(client, as_of="2020-06-05T08:00", series="UNRATE")["data"]

    assert pick(series(data["known"], "UNRATE")["latest"], "period", "value") == (
        "2020-04-01",
        14.7,
    )
    later = series(data["not_yet_known"], "UNRATE")
    assert later["period"] == "2020-04-01"
    assert [pick(v, "value", "vintage_date") for v in later["revisions"]] == [
        (14.8, "2021-01-08")
    ]


def test_at_the_close_june_5s_bar_is_known(client: TestClient) -> None:
    data = snapshot(client, as_of="2020-06-05T16:00", tickers="AAPL")["data"]

    assert company(data["known"], "AAPL")["latest_bar"]["session_date"] == "2020-06-05"
    # The fixtures' next bar is July 2's.
    assert company(data["not_yet_known"], "AAPL")["next_bar"]["session_date"] == (
        "2020-07-02"
    )


def test_a_restated_quarter_is_a_later_version(client: TestClient) -> None:
    # On November 1, 2021, Apple's latest quarter is its fourth of fiscal 2021, the
    # full year minus nine months. A made-up 10-K/A restates the year on December 15.
    data = snapshot(client, as_of="2021-11-01", tickers="AAPL")["data"]

    latest = company(data["known"], "AAPL")["latest_revenue"]
    [restated] = company(data["not_yet_known"], "AAPL")["later_revenue"]
    assert pick(latest, "value", "derived", "accession_numbers") == (
        83360000000.0,
        True,
        ["0000320193-21-000105", "0000320193-21-000065"],
    )
    assert pick(restated, "value", "derived", "accession_numbers", "available_at") == (
        82543000000.0,
        True,
        ["0000320193-21-900001", "0000320193-21-000065"],
        "2021-12-15T16:30:00-05:00",
    )


def test_nothing_after_the_data_versions_cut_shows(client: TestClient) -> None:
    # The fixtures' canary rows, known in 2099, come after the version was cut.
    data = snapshot(client, as_of="2026-01-01", tickers="AAPL")["data"]
    apple = company(data["not_yet_known"], "AAPL")

    assert apple["next_bar"] is None
    assert apple["next_filings"] == {"10-K": None, "10-Q": None, "8-K": None}
    assert apple["universe_changes"] == []


def test_the_response_echoes_one_data_version(client: TestClient) -> None:
    body = snapshot(client, **JUNE_5)

    assert (body["knowledge_time"], body["data_version"], body["reason"]) == (
        "2020-06-05T09:30:00-04:00",
        FIXTURE_DATA_VERSION,
        None,
    )


def test_tickers_are_resolved_at_the_knowledge_time(client: TestClient) -> None:
    data = snapshot(client, as_of="2020-06-05", tickers="fb")["data"]

    assert pick(company(data["known"], "FB"), "company_name", "cik") == (
        "Facebook, Inc.",
        1326801,
    )


def test_entries_count_once_in_the_order_given(client: TestClient) -> None:
    data = snapshot(
        client, as_of="2020-06-05", tickers=" tsla, AAPL,aapl,,", series="unrate"
    )["data"]

    for section in ("known", "not_yet_known"):
        assert [c["ticker"] for c in data[section]["companies"]] == ["TSLA", "AAPL"]
        assert [s["series_id"] for s in data[section]["series"]] == ["UNRATE"]


def test_series_alone_need_no_tickers(client: TestClient) -> None:
    data = snapshot(client, as_of="2020-06-05", series="PAYEMS")["data"]

    assert data["known"] == {
        "companies": [],
        "series": [{"series_id": "PAYEMS", "latest": None}],
    }
    assert data["not_yet_known"]["series"] == [
        {"series_id": "PAYEMS", "period": None, "revisions": []}
    ]


@pytest.mark.parametrize(
    ("params", "code", "message"),
    [
        (
            {"tickers": "META"},
            "unknown_ticker",
            (
                "No security in our data used the ticker META as of June 5, 2020, "
                "9:30 AM ET."
            ),
        ),
        (
            {"tickers": "AAPL", "series": "DGS10"},
            "unknown_series",
            "DGS10 isn't a series in our catalog.",
        ),
    ],
)
def test_an_unknown_entry_fails_the_request(
    client: TestClient, params: dict[str, str], code: str, message: str
) -> None:
    response = client.get("/v1/snapshot", params={"as_of": "2020-06-05", **params})

    assert response.status_code == 404
    assert response.json()["error"] == {"code": code, "message": message, "details": []}


@pytest.mark.parametrize(
    ("params", "field", "message"),
    [
        ({}, "tickers", "tickers or series is required."),
        ({"tickers": " , ", "series": ""}, "tickers", "tickers or series is required."),
        (
            {"tickers": ",".join(f"T{n}" for n in range(11))},
            "tickers",
            "tickers can list at most 10.",
        ),
        (
            {"series": ",".join(f"S{n}" for n in range(11))},
            "series",
            "series can list at most 10.",
        ),
    ],
)
def test_invalid_lists_are_422(
    client: TestClient, params: dict[str, str], field: str, message: str
) -> None:
    response = client.get("/v1/snapshot", params={"as_of": "2020-06-05", **params})

    assert response.status_code == 422
    assert response.json()["error"]["details"] == [{"field": field, "message": message}]
