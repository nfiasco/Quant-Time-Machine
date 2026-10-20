import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.conventions import KnowledgeTime, ValueResponse
from app.config import Settings
from app.data.errors import LookAheadError, NotFoundError
from app.main import create_app

FRONTEND = "http://localhost:3000"


def make_app() -> FastAPI:
    # Built from known settings, so a developer's backend/.env can't change the results.
    return create_app(Settings(_env_file=None, cors_origins=[FRONTEND]))


client = TestClient(make_app())


def test_bare_date_echoes_knowledge_time_and_data_version() -> None:
    response = client.get("/v1/knowledge-time", params={"as_of": "2020-06-05"})

    assert response.status_code == 200
    assert response.json() == {
        "knowledge_time": "2020-06-05T13:30:00Z",
        "data_version": None,
    }


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
    assert response.json()["knowledge_time"] == "2020-06-05T13:30:00Z"


def test_unencoded_plus_sign_is_422_with_a_hint() -> None:
    # An unencoded "+" in a query string means a space.
    response = client.get("/v1/knowledge-time?as_of=2020-06-05T13:30:00+00:00")

    assert response.status_code == 422
    assert "%2B" in response.json()["detail"][0]["msg"]


@pytest.mark.parametrize("as_of", ["2020-02-30", "yesterday", "2020-03-08T02:30"])
def test_invalid_as_of_is_422(as_of: str) -> None:
    response = client.get("/v1/knowledge-time", params={"as_of": as_of})

    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["query", "as_of"]
    assert error["input"] == as_of


def test_missing_as_of_is_422() -> None:
    response = client.get("/v1/knowledge-time")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "as_of"]


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


def test_not_found_error_is_404() -> None:
    app = make_app()

    @app.get("/v1/test/missing")
    def missing() -> None:
        raise NotFoundError("ticker", "ZZZZ")

    response = TestClient(app).get("/v1/test/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "unknown ticker: ZZZZ"}


def test_look_ahead_error_is_200_with_null_value() -> None:
    app = make_app()

    @app.get("/v1/test/close")
    def close(knowledge_time: KnowledgeTime) -> ValueResponse[float]:
        raise LookAheadError(
            "the 2020-06-05 close isn't known until 20:00Z",
            knowledge_time=knowledge_time,
        )

    response = TestClient(app).get("/v1/test/close", params={"as_of": "2020-06-05"})

    assert response.status_code == 200
    assert response.json() == {
        "knowledge_time": "2020-06-05T13:30:00Z",
        "data_version": None,
        "value": None,
        "reason": "the 2020-06-05 close isn't known until 20:00Z",
    }
