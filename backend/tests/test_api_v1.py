import tempfile
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.conventions import DataResponse, KnowledgeTime
from app.api.errors import INTERNAL_ERROR_MESSAGE
from app.config import Settings
from app.data.errors import LookAheadError, NotFoundError
from app.data.timeutil import parse_knowledge_time
from app.main import create_app
from tests.fixture_loader import FIXTURE_DATA_VERSION

FRONTEND = "http://localhost:3000"

NO_STORE = tempfile.TemporaryDirectory()
"""An empty DATA_DIR, so these tests never read a developer's backend/data."""


def make_app() -> FastAPI:
    # Built from known settings, so a developer's backend/.env can't change the results.
    return create_app(
        Settings(_env_file=None, cors_origins=[FRONTEND], data_dir=Path(NO_STORE.name))
    )


client = TestClient(make_app())


def test_bare_date_echoes_knowledge_time_and_data_version(
    client: TestClient,
) -> None:
    # The fixture store's client: the data version is the store's newest.
    response = client.get("/v1/knowledge-time", params={"as_of": "2020-06-05"})

    assert response.status_code == 200
    assert response.json() == {
        "knowledge_time": "2020-06-05T09:30:00-04:00",
        "data_version": FIXTURE_DATA_VERSION,
    }


def test_a_store_without_data_versions_echoes_null() -> None:
    response = client.get("/v1/knowledge-time", params={"as_of": "2020-06-05"})

    assert response.json()["data_version"] is None


@pytest.mark.parametrize(
    "as_of",
    [
        "2020-06-05T09:30",
        "2020-06-05T09:30:00-04:00",
        "2020-06-05T13:30Z",
        # The client encodes "+" as %2B, as a browser's URLSearchParams does.
        "2020-06-05T13:30:00+00:00",
    ],
)
def test_timestamps_resolve_to_one_instant(as_of: str) -> None:
    response = client.get("/v1/knowledge-time", params={"as_of": as_of})

    assert response.status_code == 200
    assert response.json()["knowledge_time"] == "2020-06-05T09:30:00-04:00"


@pytest.mark.parametrize(
    ("as_of", "echoed"),
    [
        ("2020-01-15", "2020-01-15T09:30:00-05:00"),  # winter: EST
        ("2020-06-05T13:30:00.5Z", "2020-06-05T09:30:00.500000-04:00"),
    ],
)
def test_knowledge_time_is_echoed_in_new_york_time(as_of: str, echoed: str) -> None:
    response = client.get("/v1/knowledge-time", params={"as_of": as_of})

    assert response.json()["knowledge_time"] == echoed


def test_unencoded_plus_sign_is_422_with_a_hint() -> None:
    # An unencoded "+" in a query string means a space.
    response = client.get("/v1/knowledge-time?as_of=2020-06-05T13:30:00+00:00")

    assert response.status_code == 422
    [detail] = response.json()["error"]["details"]
    assert detail["field"] == "as_of"
    assert "%2B" in detail["message"]


@pytest.mark.parametrize(
    "as_of",
    [
        "2020-02-30",
        "yesterday",
        "2020-03-08T02:30",  # never happened: clocks jumped from 2:00 to 3:00 AM
        "2020-11-01T01:30",  # happened twice: clocks went back from 2:00 to 1:00 AM
    ],
)
def test_invalid_as_of_is_422(as_of: str) -> None:
    response = client.get("/v1/knowledge-time", params={"as_of": as_of})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["details"] == [{"field": "as_of", "message": error["message"]}]


def test_a_time_that_never_happened_says_what_to_do() -> None:
    response = client.get("/v1/knowledge-time", params={"as_of": "2020-03-08T02:30"})

    assert response.json()["error"]["message"] == (
        "2:30 AM on March 8, 2020 never happened in New York: clocks jumped from 2:00 "
        "to 3:00 AM. Add an offset, or choose another time."
    )


def test_missing_as_of_is_422() -> None:
    response = client.get("/v1/knowledge-time")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "as_of is required.",
            "details": [{"field": "as_of", "message": "as_of is required."}],
        }
    }


def test_every_invalid_field_is_listed() -> None:
    app = make_app()

    @app.get("/v1/test/fields")
    def fields(
        limit: Annotated[int, Query(ge=1, le=1000)], include: bool = False
    ) -> None:
        pass

    response = TestClient(app).get(
        "/v1/test/fields", params={"limit": 0, "include": "maybe"}
    )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "invalid_request",
        "message": "limit must be at least 1. include must be true or false.",
        "details": [
            {"field": "limit", "message": "limit must be at least 1."},
            {"field": "include", "message": "include must be true or false."},
        ],
    }


def test_cors_preflight_allows_the_frontend() -> None:
    response = client.options(
        "/v1/knowledge-time",
        headers={"Origin": FRONTEND, "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND


def test_cors_refuses_other_origins() -> None:
    preflight = client.options(
        "/v1/knowledge-time",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    response = client.get(
        "/v1/knowledge-time",
        params={"as_of": "2020-06-05"},
        headers={"Origin": "https://example.com"},
    )

    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize(
    ("error", "code", "message"),
    [
        (
            NotFoundError("ticker", "zzzz"),
            "unknown_ticker",
            "No security in our data used the ticker ZZZZ.",
        ),
        (
            NotFoundError(
                "ticker", "META", knowledge_time=parse_knowledge_time("2020-06-05")
            ),
            "unknown_ticker",
            (
                "No security in our data used the ticker META as of June 5, 2020, "
                "9:30 AM ET."
            ),
        ),
        (
            NotFoundError("series", "dgs10"),
            "unknown_series",
            "DGS10 isn't a series in our catalog.",
        ),
    ],
)
def test_not_found_error_is_404(error: NotFoundError, code: str, message: str) -> None:
    app = make_app()

    @app.get("/v1/test/missing")
    def missing() -> None:
        raise error

    response = TestClient(app).get("/v1/test/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": code, "message": message, "details": []}
    }


def test_look_ahead_error_is_200_with_null_data() -> None:
    app = make_app()

    @app.get("/v1/test/close")
    def close(knowledge_time: KnowledgeTime) -> DataResponse[float | None]:
        raise LookAheadError(
            "the 2020-06-05 close isn't known until 20:00Z",
            knowledge_time=knowledge_time,
        )

    response = TestClient(app).get("/v1/test/close", params={"as_of": "2020-06-05"})

    assert response.status_code == 200
    assert response.json() == {
        "knowledge_time": "2020-06-05T09:30:00-04:00",
        "data_version": None,
        "data": None,
        "reason": "the 2020-06-05 close isn't known until 20:00Z",
    }


def test_a_reason_comes_exactly_when_data_is_empty() -> None:
    known = {"knowledge_time": parse_knowledge_time("2020-06-05"), "data_version": None}

    DataResponse[list[int]](**known, data=[], reason="Nothing was filed yet.")
    DataResponse[list[int]](**known, data=[1])
    with pytest.raises(ValidationError, match="reason"):
        DataResponse[list[int]](**known, data=[])
    with pytest.raises(ValidationError, match="reason"):
        DataResponse[int | None](**known, data=1, reason="Not empty, so no reason.")


def test_an_unhandled_error_is_a_generic_500_the_page_can_read() -> None:
    app = make_app()

    @app.get("/v1/test/bug")
    def bug() -> None:
        raise RuntimeError("internal details that must not leak")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/v1/test/bug", headers={"Origin": FRONTEND}
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": INTERNAL_ERROR_MESSAGE,
            "details": [],
        }
    }
    assert "must not leak" not in response.text
    # CORS wraps the error middleware, so the browser can read the body.
    assert response.headers["access-control-allow-origin"] == FRONTEND


def test_unknown_paths_and_methods_use_the_error_body() -> None:
    missing = client.get("/v1/nope")
    wrong_method = client.post("/v1/knowledge-time")

    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "not_found",
            "message": "There's no endpoint at /v1/nope.",
            "details": [],
        }
    }
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in wrong_method.headers["allow"]
