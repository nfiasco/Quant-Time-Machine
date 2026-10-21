import json
import traceback
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from app.config import Settings, get_settings
from app.data.http import (
    FetchError,
    MissingSettingError,
    RateLimit,
    RateLimiter,
    RateLimitExceeded,
    SourceClient,
    client_for,
)
from app.data.raw_cache import RawCache, redact_url

FRED_KEY = "fredkey0123456789abcdef0123456789"
TIINGO_TOKEN = "tiingotoken0123456789abcdef"
NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


class FakeClock:
    """A clock that moves only when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = NOW
        self.sleeps: list[float] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)


Reply = httpx2.Response | Callable[[httpx2.Request], httpx2.Response]


class FakeServer:
    """Answers requests with canned replies, in order, and records the requests."""

    def __init__(self, *replies: Reply) -> None:
        self.replies = list(replies)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply(request) if callable(reply) else reply


def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        fred_api_key=FRED_KEY,
        tiingo_api_key=TIINGO_TOKEN,
        sec_user_agent="Quant Time Machine tests test@example.com",
    )


def client(
    tmp_path: Path, source: str, server: FakeServer, clock: FakeClock, **options: object
) -> SourceClient:
    return client_for(
        source,
        settings(tmp_path),
        transport=httpx2.MockTransport(server),
        clock=clock,
        sleep=clock.sleep,
        **options,
    )


def saved_files(tmp_path: Path) -> list[Path]:
    return [path for path in (tmp_path / "raw").rglob("*") if path.is_file()]


def ok(body: object) -> httpx2.Response:
    return httpx2.Response(200, json=body)


def test_cached_response_makes_no_request(tmp_path: Path) -> None:
    server, clock = FakeServer(ok({"seriess": [{"id": "UNRATE"}]})), FakeClock()

    with client(tmp_path, "fred", server, clock) as fred:
        first = fred.get("series", {"series_id": "UNRATE"})
        second = fred.get("series", {"series_id": "UNRATE"})
    # A later run reuses the cache too.
    with client(tmp_path, "fred", server, clock) as fred:
        third = fred.get("series", {"series_id": "UNRATE"})

    assert len(server.requests) == 1
    assert (
        first.json() == second.json() == third.json() == {"seriess": [{"id": "UNRATE"}]}
    )
    assert third.fetched_at == NOW


def test_refresh_downloads_again(tmp_path: Path) -> None:
    server, clock = FakeServer(ok({"v": 1}), ok({"v": 2})), FakeClock()
    with client(tmp_path, "fred", server, clock) as fred:
        fred.get("series", {"series_id": "UNRATE"})

    with client(tmp_path, "fred", server, clock, refresh=True) as fred:
        response = fred.get("series", {"series_id": "UNRATE"})

    assert len(server.requests) == 2
    assert response.json() == {"v": 2}
    with client(tmp_path, "fred", server, clock) as fred:
        assert fred.get("series", {"series_id": "UNRATE"}).json() == {"v": 2}


def test_api_key_is_sent_but_never_saved(tmp_path: Path) -> None:
    server, clock = FakeServer(ok({"seriess": []})), FakeClock()

    with client(tmp_path, "fred", server, clock) as fred:
        response = fred.get("series", {"series_id": "UNRATE"})

    assert server.requests[0].url.params["api_key"] == FRED_KEY
    assert saved_files(tmp_path)
    for path in saved_files(tmp_path):
        assert FRED_KEY.encode() not in path.read_bytes()
    expected = "https://api.stlouisfed.org/fred/series?file_type=json&series_id=UNRATE"
    assert response.url == expected
    [metadata] = (tmp_path / "raw" / "fred").rglob("*.json")
    record = json.loads(metadata.read_text())
    assert record["url"] == expected
    assert record["status_code"] == 200
    assert record["fetched_at"] == "2026-10-19T12:00:00+00:00"


def test_tiingo_token_goes_in_a_header_that_is_never_saved(tmp_path: Path) -> None:
    server, clock = FakeServer(ok({"ticker": "AAPL"})), FakeClock()

    with client(tmp_path, "tiingo", server, clock) as tiingo:
        tiingo.get("tiingo/daily/AAPL")

    assert server.requests[0].headers["authorization"] == f"Token {TIINGO_TOKEN}"
    for path in saved_files(tmp_path):
        assert TIINGO_TOKEN.encode() not in path.read_bytes()


def test_sec_requests_carry_the_user_agent(tmp_path: Path) -> None:
    server, clock = FakeServer(ok({"cik": "320193"})), FakeClock()

    with client(tmp_path, "sec", server, clock) as sec:
        sec.get("submissions/CIK0000320193.json")

    request = server.requests[0]
    assert request.url == "https://data.sec.gov/submissions/CIK0000320193.json"
    assert request.headers["user-agent"] == "Quant Time Machine tests test@example.com"


def unreachable(request: httpx2.Request) -> httpx2.Response:
    # httpx2's real errors put the full URL, API key included, in their message.
    raise httpx2.ConnectError(f"can't reach {request.url}", request=request)


@pytest.mark.parametrize(
    "reply", [unreachable, httpx2.Response(500, text="server error")]
)
def test_failures_never_reveal_the_key(tmp_path: Path, reply: Reply) -> None:
    server, clock = FakeServer(reply), FakeClock()

    with (
        client(tmp_path, "fred", server, clock) as fred,
        pytest.raises(FetchError, match="after 4 attempts") as caught,
    ):
        fred.get("series", {"series_id": "UNRATE"})

    report = "".join(traceback.format_exception(caught.value))
    assert FRED_KEY not in report
    assert "series_id=UNRATE" in report
    assert saved_files(tmp_path) == []


def test_server_errors_are_retried_with_backoff(tmp_path: Path) -> None:
    server = FakeServer(httpx2.Response(503), httpx2.Response(503), ok({"ok": True}))
    clock = FakeClock()

    with client(tmp_path, "fred", server, clock) as fred:
        response = fred.get("series", {"series_id": "UNRATE"})

    assert response.json() == {"ok": True}
    assert len(server.requests) == 3
    assert clock.sleeps == [1.0, 2.0]


def test_retry_after_is_honored(tmp_path: Path) -> None:
    busy = httpx2.Response(429, headers={"Retry-After": "7"})
    server, clock = FakeServer(busy, ok({"ok": True})), FakeClock()

    with client(tmp_path, "fred", server, clock) as fred:
        fred.get("series", {"series_id": "UNRATE"})

    assert clock.sleeps == [7.0]


def test_a_long_retry_after_stops_the_run(tmp_path: Path) -> None:
    busy = httpx2.Response(429, headers={"Retry-After": "3600"})
    server, clock = FakeServer(busy), FakeClock()

    with (
        client(tmp_path, "tiingo", server, clock) as tiingo,
        pytest.raises(RateLimitExceeded) as caught,
    ):
        tiingo.get("tiingo/daily/AAPL/prices")

    assert caught.value.retry_at == NOW + timedelta(hours=1)
    assert len(server.requests) == 1
    assert clock.sleeps == []


def test_client_errors_are_not_retried(tmp_path: Path) -> None:
    server, clock = FakeServer(httpx2.Response(404)), FakeClock()

    with (
        client(tmp_path, "sec", server, clock) as sec,
        pytest.raises(FetchError, match="after 1 attempt: HTTP 404"),
    ):
        sec.get("submissions/CIK0000000000.json")

    assert len(server.requests) == 1
    assert saved_files(tmp_path) == []


def test_rate_limiter_spaces_requests() -> None:
    clock = FakeClock()
    limiter = RateLimiter(
        "test",
        [RateLimit(2, timedelta(seconds=1))],
        clock=clock,
        sleep=clock.sleep,
        max_wait=timedelta(seconds=60),
    )

    for _ in range(5):
        limiter.acquire()

    # Two requests per second: the 3rd waits for the 1st to leave the window, and so on.
    assert clock.sleeps == [1.0, 1.0]
    assert clock.now == NOW + timedelta(seconds=2)


def test_rate_limiter_stops_instead_of_waiting_long() -> None:
    clock = FakeClock()
    history = [NOW - timedelta(minutes=50) + timedelta(seconds=i) for i in range(50)]
    limiter = RateLimiter(
        "tiingo",
        [RateLimit(50, timedelta(hours=1))],
        clock=clock,
        sleep=clock.sleep,
        max_wait=timedelta(seconds=60),
        history=history,
    )

    with pytest.raises(RateLimitExceeded) as caught:
        limiter.acquire()

    assert caught.value.retry_at == history[0] + timedelta(hours=1)
    assert clock.sleeps == []


def test_tiingo_limit_counts_requests_from_earlier_runs(tmp_path: Path) -> None:
    cache = RawCache(tmp_path / "raw", "tiingo")
    for minute in range(50):
        cache.put(
            "GET",
            f"https://api.tiingo.com/tiingo/daily/T{minute}",
            status_code=200,
            content=b"{}",
            headers={},
            fetched_at=NOW - timedelta(minutes=minute),
        )
    server, clock = FakeServer(ok({})), FakeClock()

    with (
        client(tmp_path, "tiingo", server, clock) as tiingo,
        pytest.raises(RateLimitExceeded),
    ):
        tiingo.get("tiingo/daily/AAPL")

    assert server.requests == []


@pytest.mark.parametrize(
    ("source", "setting"),
    [("sec", "SEC_USER_AGENT"), ("fred", "FRED_API_KEY"), ("tiingo", "TIINGO_API_KEY")],
)
def test_missing_settings_are_named(tmp_path: Path, source: str, setting: str) -> None:
    with pytest.raises(MissingSettingError, match=setting):
        client_for(source, Settings(_env_file=None, data_dir=tmp_path))


def test_unknown_sources_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown source"):
        client_for("wrds", settings(tmp_path))


def test_redact_url_sorts_the_query_and_drops_secrets() -> None:
    url = "https://example.com/path?token=t&b=2&api_key=k&APIKEY=k&a=1"

    assert redact_url(url) == "https://example.com/path?a=1&b=2"


LIVE = [
    ("sec", "sec_user_agent", "submissions/CIK0000320193.json", None, "cik"),
    ("fred", "fred_api_key", "series", {"series_id": "UNRATE"}, "seriess"),
    ("tiingo", "tiingo_api_key", "tiingo/daily/AAPL", None, "ticker"),
]


@pytest.mark.network
@pytest.mark.parametrize(("source", "setting", "path", "params", "field"), LIVE)
def test_live_request(
    tmp_path: Path,
    source: str,
    setting: str,
    path: str,
    params: dict[str, str] | None,
    field: str,
) -> None:
    # One request per source, into a temporary cache. Tiingo's counts against its
    # 50 per hour.
    live = get_settings()
    if getattr(live, setting) is None:
        pytest.skip(f"{setting.upper()} isn't set in backend/.env")

    with client_for(source, live.model_copy(update={"data_dir": tmp_path})) as http:
        response = http.get(path, params)

    assert response.status_code == 200
    assert field in response.json()
    secrets = [live.fred_api_key, live.tiingo_api_key]
    for secret in (s.get_secret_value().encode() for s in secrets if s is not None):
        for saved in saved_files(tmp_path):
            assert secret not in saved.read_bytes()
