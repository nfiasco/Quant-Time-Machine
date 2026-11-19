"""The cache of as-of answers (S8.6): app/api/cache.py, and doc/reference/api-v1.md,
"Caching"."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import conventions
from app.api.cache import Answer, Key, ResponseCache
from app.config import Settings
from app.data.store import write_rows
from app.data.tables import TABLES
from app.data.versions import write_manifest
from app.main import create_app
from tests.fixture_loader import (
    FIXTURE_DATA_VERSION,
    FIXTURE_INGESTED_AT,
    TEST_OBSERVATIONS,
    TEST_TABLES,
)

MACRO = "/v1/macro/UNRATE?as_of=2020-06-05"
HIT = "qtm-api; hit"
MISS = "qtm-api; fwd=miss; stored"
FRONTEND = "http://localhost:3000"

SPEC = create_app(Settings(_env_file=None)).openapi()


def documented_as_of_requests() -> list[str]:
    """Each GET with `as_of` that a documented 200 example comes from."""
    urls = set()
    for operations in SPEC["paths"].values():
        for operation in operations.values():
            ok = operation["responses"].get("200", {})
            content = ok.get("content", {}).get("application/json", {})
            for example in content.get("examples", {}).values():
                method, url = example["description"].split(" ", 1)
                if method == "GET" and "as_of=" in url:
                    urls.add(url)
    return sorted(urls)


def test_a_repeat_is_answered_from_the_cache(client: TestClient) -> None:
    first = client.get(MACRO)
    second = client.get(MACRO)

    assert (first.status_code, second.status_code) == (200, 200)
    assert (first.headers["cache-status"], second.headers["cache-status"]) == (
        MISS,
        HIT,
    )
    assert second.content == first.content
    assert second.headers["etag"] == first.headers["etag"]
    assert second.headers["cache-control"] == "no-cache"
    assert second.headers["content-type"] == "application/json"


@pytest.mark.parametrize("url", documented_as_of_requests())
def test_every_documented_as_of_request_is_cached(client: TestClient, url: str) -> None:
    # So a router that forgets route_class=AsOfRoute shows up here.
    client.get(url)

    assert client.get(url).headers.get("cache-status") == HIT


@pytest.mark.parametrize(
    "as_of", ["2020-06-05T09:30", "2020-06-05T13:30:00Z", "2020-06-05T09:30:00-04:00"]
)
def test_the_same_instant_written_another_way_shares_an_answer(
    client: TestClient, as_of: str
) -> None:
    first = client.get("/v1/macro/UNRATE", params={"as_of": "2020-06-05"})

    again = client.get("/v1/macro/UNRATE", params={"as_of": as_of})

    assert again.headers["cache-status"] == HIT
    assert again.content == first.content


def test_other_parameters_are_part_of_the_key(client: TestClient) -> None:
    client.get("/v1/snapshot", params={"as_of": "2020-06-05", "tickers": "AAPL"})

    other = client.get(
        "/v1/snapshot", params={"as_of": "2020-06-05", "tickers": "TSLA"}
    )

    assert other.headers["cache-status"] == MISS
    assert [c["ticker"] for c in other.json()["data"]["known"]["companies"]] == ["TSLA"]


def test_each_path_is_its_own_key(client: TestClient) -> None:
    apple = client.get("/v1/prices/AAPL", params={"as_of": "2020-06-05"})

    tesla = client.get("/v1/prices/TSLA", params={"as_of": "2020-06-05"})

    assert tesla.headers["cache-status"] == MISS
    assert apple.json()["data"]["ticker"] == "AAPL"
    assert tesla.json()["data"] is None  # the fixtures have no TSLA bars


def test_a_repeated_parameter_keeps_its_order_in_the_key(client: TestClient) -> None:
    # The API reads the last of a repeated parameter, so these ask for different tickers.
    tesla = client.get("/v1/snapshot?as_of=2020-06-05&tickers=AAPL&tickers=TSLA")

    apple = client.get("/v1/snapshot?as_of=2020-06-05&tickers=TSLA&tickers=AAPL")

    assert apple.headers["cache-status"] == MISS
    assert [c["ticker"] for c in tesla.json()["data"]["known"]["companies"]] == ["TSLA"]
    assert [c["ticker"] for c in apple.json()["data"]["known"]["companies"]] == ["AAPL"]


def test_an_answer_never_reaches_an_earlier_moment(client: TestClient) -> None:
    # At 09:30 on June 5, 2020, May's unemployment rate was out, published at 08:30.
    # Half an hour earlier only April's was: the cached answer must not leak into it.
    may = client.get("/v1/macro/UNRATE", params={"as_of": "2020-06-05T09:30"})

    april = client.get("/v1/macro/UNRATE", params={"as_of": "2020-06-05T08:00"})

    assert may.json()["data"]["period"] == "2020-05-01"
    assert april.headers["cache-status"] == MISS
    assert april.json()["data"]["period"] == "2020-04-01"


@pytest.mark.parametrize("if_none_match", ["{etag}", "W/{etag}", '"0123", {etag}', "*"])
def test_a_request_naming_the_etag_gets_a_304(
    client: TestClient, if_none_match: str
) -> None:
    etag = client.get(MACRO).headers["etag"]

    response = client.get(
        MACRO, headers={"If-None-Match": if_none_match.format(etag=etag)}
    )

    assert response.status_code == 304
    assert response.content == b""
    assert response.headers["etag"] == etag
    assert response.headers["cache-control"] == "no-cache"


def test_a_request_naming_another_etag_gets_the_answer(client: TestClient) -> None:
    answer = client.get(MACRO)

    response = client.get(MACRO, headers={"If-None-Match": '"0123"'})

    assert response.status_code == 200
    assert response.content == answer.content


def test_a_new_data_version_starts_the_cache_over(
    client: TestClient, fixture_store: Path
) -> None:
    before = client.get(MACRO)
    later = FIXTURE_INGESTED_AT + timedelta(days=1)
    write_rows(
        fixture_store,
        TEST_OBSERVATIONS,
        [
            {
                "series_id": "TEST",
                "period": date(2020, 9, 1),
                "value": 1.0,
                "source": "test",
                "source_ref": "synthetic: 2020-09-01",
                "available_at": datetime(2020, 10, 1, tzinfo=UTC),
                "time_assumed": False,
            }
        ],
        now=later,
    )
    version = write_manifest(fixture_store, (TABLES | TEST_TABLES).values(), now=later)

    after = client.get(MACRO)

    assert version is not None and version.data_version != FIXTURE_DATA_VERSION
    assert after.headers["cache-status"] == MISS
    assert before.json()["data_version"] == FIXTURE_DATA_VERSION
    assert after.json()["data_version"] == version.data_version
    assert after.headers["etag"] != before.headers["etag"]


def test_a_miss_reads_the_data_version_its_key_names(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The cache looks the newest data version up, and the route reads that one rather
    # than looking again. So an answer is kept under the version it was built from, even
    # when a newer one appears while it's built.
    def look_again(store: Path) -> str | None:
        raise AssertionError("the route looked the data version up again")

    monkeypatch.setattr(conventions, "latest_data_version", look_again)

    response = client.get(MACRO)

    assert response.headers["cache-status"] == MISS
    assert response.json()["data_version"] == FIXTURE_DATA_VERSION


def test_a_store_without_a_data_version_isnt_cached(tmp_path: Path) -> None:
    # Its view reads whatever files are there now, so its answers can change.
    client = TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path)))

    for _ in range(2):
        response = client.get("/v1/knowledge-time", params={"as_of": "2020-06-05"})
        assert response.json()["data_version"] is None
        assert "cache-status" not in response.headers
        assert "etag" not in response.headers


@pytest.mark.parametrize(
    "url",
    [
        "/v1/prices/NOPE?as_of=2020-06-05",  # 404 unknown_ticker
        "/v1/macro/UNRATE?as_of=2020-06-05T25:00",  # 422
        "/v1/macro/UNRATE",  # 422: as_of is required
    ],
)
def test_errors_arent_cached(client: TestClient, url: str) -> None:
    for _ in range(2):
        response = client.get(url)
        assert response.status_code in (404, 422)
        assert "cache-status" not in response.headers


def test_answers_without_as_of_arent_cached(client: TestClient) -> None:
    for _ in range(2):
        response = client.get("/v1/catalog/signals")
        assert response.status_code == 200
        assert "cache-status" not in response.headers


def test_a_cached_answer_carries_the_cors_headers(client: TestClient) -> None:
    client.get(MACRO, headers={"Origin": FRONTEND})

    hit = client.get(MACRO, headers={"Origin": FRONTEND})

    assert hit.headers["cache-status"] == HIT
    assert hit.headers["access-control-allow-origin"] == FRONTEND


def test_the_cache_can_be_turned_off(fixture_store: Path) -> None:
    settings = Settings(
        _env_file=None, data_dir=fixture_store.parent, response_cache_mb=0
    )
    client = TestClient(create_app(settings))

    for _ in range(2):
        response = client.get(MACRO)
        assert response.status_code == 200
        assert "cache-status" not in response.headers
        assert "etag" not in response.headers


def key(path: str) -> Key:
    return path, "2020-06-05T13:30:00+00:00", ()


def answer(size: int) -> Answer:
    return Answer.of(b"x" * size, "application/json")


def test_the_answers_used_longest_ago_go_first() -> None:
    answers = ResponseCache(max_bytes=10)
    assert answers.get("v1", key("/a")) is None
    answers.put("v1", key("/a"), answer(4))
    answers.put("v1", key("/b"), answer(4))
    answers.get("v1", key("/a"))  # now /b was used longest ago

    answers.put("v1", key("/c"), answer(4))

    assert answers.get("v1", key("/b")) is None
    assert answers.get("v1", key("/a")) is not None
    assert answers.get("v1", key("/c")) is not None
    assert (len(answers), answers.bytes) == (2, 8)


def test_an_answer_bigger_than_the_cache_isnt_kept() -> None:
    answers = ResponseCache(max_bytes=10)
    answers.get("v1", key("/a"))

    assert answers.put("v1", key("/a"), answer(11)) is False
    assert (len(answers), answers.bytes) == (0, 0)


def test_another_data_version_starts_the_cache_over() -> None:
    answers = ResponseCache(max_bytes=10)
    answers.get("v1", key("/a"))
    answers.put("v1", key("/a"), answer(4))

    assert answers.get("v2", key("/a")) is None
    assert (len(answers), answers.bytes) == (0, 0)
    # An answer built from v1 that arrives now is too late.
    assert answers.put("v1", key("/a"), answer(4)) is False
    assert len(answers) == 0
