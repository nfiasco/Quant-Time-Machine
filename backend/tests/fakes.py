"""Fakes for tests that download: a clock that only moves when code sleeps, and a server
that answers with canned replies. Ingester tests build a client on them with
`fake_client`, so nothing touches the network."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2

from app.config import Settings
from app.data.http import SourceClient, client_for

FRED_KEY = "fredkey0123456789abcdef0123456789"
TIINGO_TOKEN = "tiingotoken0123456789abcdef"
NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


class FakeClock:
    """A clock that moves only when the code under test sleeps."""

    def __init__(self, now: datetime = NOW) -> None:
        self.now = now
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
    """Settings with test credentials and DATA_DIR in a temporary folder."""
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        fred_api_key=FRED_KEY,
        tiingo_api_key=TIINGO_TOKEN,
        sec_user_agent="Quant Time Machine tests test@example.com",
    )


def fake_client(
    tmp_path: Path, source: str, server: FakeServer, clock: FakeClock, **options: object
) -> SourceClient:
    """A client for `source` that sends its requests to `server`."""
    return client_for(
        source,
        settings(tmp_path),
        transport=httpx2.MockTransport(server),
        clock=clock,
        sleep=clock.sleep,
        **options,
    )


def ok(body: object) -> httpx2.Response:
    return httpx2.Response(200, json=body)
