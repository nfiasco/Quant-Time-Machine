"""Example responses for the OpenAPI docs at /docs, one set per route (S8.2).

Each example's description is the request that produces it. tests/test_api_examples.py
replays every one against the test fixtures and requires the same answer, so an example
can't drift from what the API returns. The macro and filing examples are real SEC and
FRED values. The price example is made up, because Tiingo's terms don't allow sharing
its data (D2).
"""

from typing import Any

from fastapi import FastAPI

from app.api.errors import ErrorResponse

type Responses = dict[int | str, dict[str, Any]]


def example(request: str, summary: str, value: object) -> dict[str, Any]:
    """One named example: `request` is the GET it answers, such as /v1/prices/AAPL?…"""
    return {"summary": summary, "description": f"GET {request}", "value": value}


def _ok(**examples: dict[str, Any]) -> dict[str, Any]:
    return {"content": {"application/json": {"examples": examples}}}


def _error(description: str, **examples: dict[str, Any]) -> dict[str, Any]:
    return {"model": ErrorResponse, "description": description, **_ok(**examples)}


def _error_body(code: str, message: str, field: str | None = None) -> dict[str, Any]:
    details = [] if field is None else [{"field": field, "message": message}]
    return {"error": {"code": code, "message": message, "details": details}}


def _known_at(
    knowledge_time: str, data: object, reason: str | None = None
) -> dict[str, Any]:
    return {
        "knowledge_time": knowledge_time,
        "data_version": None,
        "data": data,
        "reason": reason,
    }


JUNE_5_2020 = "2020-06-05T09:30:00-04:00"

V1_ERRORS: Responses = {
    422: {"model": ErrorResponse, "description": "A parameter is missing or invalid"},
    500: {"model": ErrorResponse, "description": "A bug. The message is generic."},
}
"""The errors every /v1 endpoint can answer with. A route's own entries replace these."""

_UNRATE = {
    "series_id": "UNRATE",
    "title": "Unemployment Rate",
    "units": "Percent",
    "frequency": "Monthly",
    "seasonal_adjustment": "Seasonally Adjusted",
    "release": "Employment Situation",
    "time_assumed": False,
    "source": "alfred",
}

_DST_GAP = (
    "2:30 AM on March 8, 2020 never happened in New York: clocks jumped from 2:00 to "
    "3:00 AM. Add an offset, or choose another time."
)

MACRO: Responses = {
    200: _ok(
        after_jobs_report=example(
            "/v1/macro/UNRATE?as_of=2020-06-05",
            "May 2020's first print, from the 08:30 jobs report",
            _known_at(
                JUNE_5_2020,
                {
                    **_UNRATE,
                    "period": "2020-05-01",
                    "value": 13.3,
                    "vintage_date": "2020-06-05",
                    "available_at": "2020-06-05T08:30:00-04:00",
                    "source_ref": "UNRATE vintage 2020-06-05",
                },
            ),
        ),
        before_jobs_report=example(
            "/v1/macro/UNRATE?as_of=2020-06-05T08:00",
            "Half an hour earlier, the latest value is April's first print",
            _known_at(
                "2020-06-05T08:00:00-04:00",
                {
                    **_UNRATE,
                    "period": "2020-04-01",
                    "value": 14.7,
                    "vintage_date": "2020-05-08",
                    "available_at": "2020-05-08T08:30:00-04:00",
                    "source_ref": "UNRATE vintage 2020-05-08",
                },
            ),
        ),
        not_published_yet=example(
            "/v1/macro/UNRATE?as_of=2020-06-05&period=2020-06-01",
            "June 2020 wasn't published until July 2",
            _known_at(
                JUNE_5_2020,
                None,
                "No UNRATE value for 2020-06-01 had been published by June 5, 2020, "
                "9:30 AM ET.",
            ),
        ),
    ),
    404: _error(
        "The series isn't in our catalog",
        unknown_series=example(
            "/v1/macro/DGS10?as_of=2020-06-05",
            "A series we don't load",
            _error_body("unknown_series", "DGS10 isn't a series in our catalog."),
        ),
    ),
    422: _error(
        "A parameter is missing or invalid",
        time_that_never_happened=example(
            "/v1/macro/UNRATE?as_of=2020-03-08T02:30",
            "A New York time skipped by daylight saving",
            _error_body("invalid_request", _DST_GAP, "as_of"),
        ),
    ),
}

PRICES: Responses = {
    200: _ok(
        june_4_close=example(
            "/v1/prices/AAPL?as_of=2020-06-05",
            "At 09:30 on June 5, the latest bar is June 4's (made-up numbers)",
            _known_at(
                JUNE_5_2020,
                {
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
            ),
        ),
    ),
    403: _error(
        "Raw prices are turned off on this deployment (SERVE_RAW_PRICES)",
        prices_restricted=example(
            "/v1/prices/AAPL?as_of=2020-06-05",
            "Until Tiingo's display terms are settled (D2)",
            _error_body(
                "prices_restricted",
                "Raw prices are turned off on this server, because our price "
                "vendor's terms don't allow showing them publicly yet.",
            ),
        ),
    ),
    404: _error(
        "No security in our data used the ticker at the knowledge time",
        meta_before_2022=example(
            "/v1/prices/META?as_of=2020-06-05",
            "Facebook traded as FB until June 9, 2022",
            _error_body(
                "unknown_ticker",
                "No security in our data used the ticker META as of June 5, 2020, "
                "9:30 AM ET.",
            ),
        ),
    ),
    422: _error(
        "A parameter is missing or invalid",
        unreadable_as_of=example(
            "/v1/prices/AAPL?as_of=yesterday",
            "as_of must be a date or a time",
            _error_body(
                "invalid_request",
                "'yesterday' isn't a knowledge time. Use a date such as 2020-06-05 "
                "(9:30 AM ET that day), a New York time such as 2020-06-05T09:30, or a "
                "time with an offset such as 2020-06-05T13:30Z.",
                "as_of",
            ),
        ),
    ),
}

_APPLE_10Q = {
    "ticker": "AAPL",
    "cik": 320193,
    "company_name": "Apple Inc.",
    "form": "10-Q",
    "is_amendment": False,
    "amends": None,
    "time_assumed": False,
    "source": "edgar",
}
_EDGAR = "https://www.sec.gov/Archives/edgar/data/320193"

_APPLE_Q2_2020 = {
    **_APPLE_10Q,
    "accession_number": "0000320193-20-000052",
    "period_of_report": "2020-03-28",
    "filing_date": "2020-05-01",
    "available_at": "2020-04-30T18:03:10-04:00",
    "document_url": f"{_EDGAR}/000032019320000052/a10-qq220203282020.htm",
    "index_url": f"{_EDGAR}/000032019320000052/0000320193-20-000052-index.htm",
    "source_ref": "0000320193-20-000052",
}

_APPLE_Q1_2020 = {
    **_APPLE_10Q,
    "accession_number": "0000320193-20-000010",
    "period_of_report": "2019-12-28",
    "filing_date": "2020-01-29",
    "available_at": "2020-01-28T18:02:44-05:00",
    "document_url": f"{_EDGAR}/000032019320000010/a10-qq1202012282019.htm",
    "index_url": f"{_EDGAR}/000032019320000010/0000320193-20-000010-index.htm",
    "source_ref": "0000320193-20-000010",
}


def _fb_before_its_ipo(path: str) -> dict[str, Any]:
    return _error(
        "No security in our data used the ticker at the knowledge time",
        fb_before_its_ipo=example(
            f"{path}?as_of=2012-05-17",
            "Facebook's shares began trading on May 18, 2012",
            _error_body(
                "unknown_ticker",
                "No security in our data used the ticker FB as of May 17, 2012, "
                "9:30 AM ET.",
            ),
        ),
    )


LATEST_FILING: Responses = {
    200: _ok(
        apple_10q=example(
            "/v1/filings/AAPL/latest?as_of=2020-06-05&form=10-Q",
            "The 10-Q accepted on April 30; the next one came on July 30",
            _known_at(JUNE_5_2020, _APPLE_Q2_2020),
        ),
        nothing_filed_yet=example(
            "/v1/filings/FB/latest?as_of=2012-05-21",
            "Three days after its IPO, Facebook hadn't filed a 10-Q",
            _known_at(
                "2012-05-21T09:30:00-04:00",
                None,
                "No 10-Q from Facebook, Inc. had been accepted by EDGAR by May 21, "
                "2012, 9:30 AM ET.",
            ),
        ),
    ),
    404: _fb_before_its_ipo("/v1/filings/FB/latest"),
    422: _error(
        "A parameter is missing or invalid",
        unknown_form=example(
            "/v1/filings/AAPL/latest?as_of=2020-06-05&form=S-1",
            "Only 10-K, 10-Q, and 8-K filings are loaded",
            _error_body(
                "invalid_request", "form must be '10-K', '10-Q' or '8-K'.", "form"
            ),
        ),
    ),
}

FILINGS: Responses = {
    200: _ok(
        apple_10qs=example(
            "/v1/filings/AAPL?as_of=2020-06-05&form=10-Q&limit=2",
            "Apple's latest two 10-Qs, newest first",
            _known_at(JUNE_5_2020, [_APPLE_Q2_2020, _APPLE_Q1_2020]),
        ),
        a_fund_files_none=example(
            "/v1/filings/SPY?as_of=2020-06-05",
            "SPY, an exchange-traded fund, files no 10-K, 10-Q, or 8-K",
            _known_at(
                JUNE_5_2020,
                [],
                "No 10-K, 10-Q, or 8-K filings from SPDR S&P 500 ETF Trust had been "
                "accepted by EDGAR by June 5, 2020, 9:30 AM ET.",
            ),
        ),
    ),
    404: _fb_before_its_ipo("/v1/filings/FB"),
    422: _error(
        "A parameter is missing or invalid",
        limit_too_high=example(
            "/v1/filings/AAPL?as_of=2020-06-05&limit=1001",
            "At most 1,000 filings per request",
            _error_body("invalid_request", "limit must be at most 1000.", "limit"),
        ),
    ),
}


def keep_nulls(app: FastAPI) -> None:
    """Make `app.openapi()` keep the nulls in these examples.

    FastAPI writes the OpenAPI spec without null values, which also strips them from
    examples, so `"data": null` and `"data_version": null` would vanish from /docs. This
    wraps `app.openapi`, FastAPI's documented hook, to put each example's value back,
    matched by its status and request.
    """
    originals = {
        (str(status), example["description"]): example["value"]
        for responses in (MACRO, PRICES, LATEST_FILING, FILINGS)
        for status, response in responses.items()
        for example in _examples_in(response).values()
    }
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        spec = generate()
        for operations in spec.get("paths", {}).values():
            for operation in operations.values():
                for status, response in operation.get("responses", {}).items():
                    for example in _examples_in(response).values():
                        key = (status, example.get("description"))
                        if key in originals:
                            example["value"] = originals[key]
        return spec

    app.openapi = openapi  # type: ignore[method-assign]


def _examples_in(response: dict[str, Any]) -> dict[str, Any]:
    return response.get("content", {}).get("application/json", {}).get("examples", {})
