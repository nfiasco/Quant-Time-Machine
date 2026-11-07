"""scripts/smoke_test.py's checks, run against the API reading the fixture store, so the
smoke test stays in step with the API it checks after each deploy (S15.1)."""

from collections.abc import Mapping

from fastapi.testclient import TestClient

from scripts.smoke_test import Get, Reply, run_checks
from tests.fixture_loader import FIXTURE_DATA_VERSION

# The tests' API allows only the default origin (app/config.py).
ORIGIN = "http://localhost:3000"


def in_process(client: TestClient) -> Get:
    def get(path: str, headers: Mapping[str, str]) -> Reply:
        response = client.get(path, headers=dict(headers))
        body = response.json() if response.content else None
        return Reply(response.status_code, dict(response.headers), body)

    return get


def failed(client: TestClient, **options: str) -> dict[str, str | None]:
    """The checks that fail, by name, with what's wrong."""
    results = run_checks(in_process(client), **({"origin": ORIGIN} | options))
    return {result.name: result.problem for result in results if result.problem}


def test_passes_against_a_public_deployment(restricted_client: TestClient) -> None:
    assert failed(restricted_client, data_version=FIXTURE_DATA_VERSION) == {}


def test_fails_when_raw_prices_are_served(client: TestClient) -> None:
    assert failed(client) == {"prices": "status 200, expected 403"}


def test_fails_when_the_answers_come_from_another_data_version(
    restricted_client: TestClient,
) -> None:
    problems = failed(restricted_client, data_version="20000101T000000Z")

    assert problems.keys() == {"macro", "filing"}
    assert "data_version is '20261019T120000Z'" in problems["macro"]


def test_fails_when_the_web_app_origin_is_not_allowed(
    restricted_client: TestClient,
) -> None:
    problems = failed(restricted_client, origin="https://example.com")

    assert problems == {
        "cors": "access-control-allow-origin is None, expected 'https://example.com'"
    }


def test_a_request_that_fails_outright_fails_only_its_check() -> None:
    def get(path: str, headers: Mapping[str, str]) -> Reply:
        if path.startswith("/v1/prices"):
            raise ConnectionRefusedError("connection refused")
        return Reply(503, {}, None)

    results = run_checks(get)

    assert [result.name for result in results] == [
        "health",
        "cors",
        "macro",
        "filing",
        "prices",
    ]
    assert results[-1].problem == "request failed: connection refused"
    assert results[0].problem == "status 503, expected 200"
