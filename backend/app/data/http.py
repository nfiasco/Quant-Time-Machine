"""A polite HTTP client for ingestion: rate limits, retries, and the raw cache (S3.4).

Each source's limits come from its terms (doc/data-sources.md):

- SEC EDGAR: at most 10 requests per second, with a User-Agent that names us and
  gives a contact email.
- FRED: about 120 requests per minute.
- Tiingo, free plan: 50 requests per hour and 1,000 per day.

`client_for(source, settings)` builds a client with the source's base URL, credentials,
and limits. `client.get(path, params)` answers from the raw cache when it can, so a
re-run makes no requests for what it already has. When a limit would mean waiting more
than a minute, the client raises RateLimitExceeded instead of sleeping, and a later run
picks up where this one stopped.

Every source answers in JSON. A successful status with anything else, such as the HTML
page FRED serves with 200 while it's down for maintenance, is a failed request: it isn't
cached, so the next run asks again.
"""

import time
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Self

import httpx2
from pydantic import SecretStr

from app.config import Settings
from app.data.raw_cache import CachedResponse, RawCache, redact_url


@dataclass(frozen=True)
class RateLimit:
    """At most `requests` requests in any window of length `per`."""

    requests: int
    per: timedelta


@dataclass(frozen=True)
class SourceConfig:
    """Where a source lives and how fast we may ask it."""

    name: str
    base_url: str
    limits: tuple[RateLimit, ...]


SOURCES: Mapping[str, SourceConfig] = {
    "sec": SourceConfig(
        "sec", "https://data.sec.gov/", (RateLimit(10, timedelta(seconds=1)),)
    ),
    "fred": SourceConfig(
        "fred",
        "https://api.stlouisfed.org/fred/",
        (RateLimit(120, timedelta(minutes=1)),),
    ),
    "tiingo": SourceConfig(
        "tiingo",
        "https://api.tiingo.com/",
        (RateLimit(50, timedelta(hours=1)), RateLimit(1000, timedelta(days=1))),
    ),
}
"""Every source ingestion can download from, by name."""

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class FetchError(Exception):
    """A request that failed for good. Its message never contains a secret."""


class RateLimitExceeded(Exception):
    """A source's rate limit is used up for longer than the client is willing to wait."""

    def __init__(self, source: str, retry_at: datetime) -> None:
        super().__init__(
            f"{source}: rate limit reached until {retry_at:%Y-%m-%d %H:%M:%S} UTC"
        )
        self.source = source
        self.retry_at = retry_at


class MissingSettingError(Exception):
    """A setting a source needs, such as its API key, isn't set."""


class RateLimiter:
    """Sliding-window rate limits for one source.

    `acquire()` waits until a request fits every limit. If that would take longer than
    `max_wait`, it raises RateLimitExceeded instead. `history` holds earlier request
    times, for example from a previous run, so they count against the limits too.
    """

    def __init__(
        self,
        source: str,
        limits: Sequence[RateLimit],
        *,
        clock: Callable[[], datetime],
        sleep: Callable[[float], None],
        max_wait: timedelta,
        history: Iterable[datetime] = (),
    ) -> None:
        self.source = source
        self._limits = limits
        self._clock = clock
        self._sleep = sleep
        self._max_wait = max_wait
        self._longest = max((limit.per for limit in limits), default=timedelta(0))
        self._times: deque[datetime] = deque(sorted(history))

    def acquire(self) -> None:
        while True:
            now = self._clock()
            while self._times and self._times[0] <= now - self._longest:
                self._times.popleft()
            ready_at = self._ready_at(now)
            if ready_at <= now:
                self._times.append(now)
                return
            if ready_at - now > self._max_wait:
                raise RateLimitExceeded(self.source, ready_at)
            self._sleep((ready_at - now).total_seconds())

    def _ready_at(self, now: datetime) -> datetime:
        """The earliest time at which one more request fits every limit."""
        ready_at = now
        for limit in self._limits:
            recent = [t for t in self._times if t > now - limit.per]
            if len(recent) >= limit.requests:
                # This request has to leave the window before another one fits.
                ready_at = max(ready_at, recent[-limit.requests] + limit.per)
        return ready_at


class SourceClient:
    """Fetches from one source, through its rate limits and the raw cache."""

    def __init__(
        self,
        config: SourceConfig,
        cache: RawCache,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        secrets: Sequence[str] = (),
        refresh: bool = False,
        transport: httpx2.BaseTransport | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] = time.sleep,
        max_wait: timedelta = timedelta(seconds=60),
        max_attempts: int = 4,
    ) -> None:
        self.config = config
        self.cache = cache
        self.refresh = refresh
        self._secrets = [secret for secret in secrets if secret]
        self._clock = clock
        self._sleep = sleep
        self._max_wait = max_wait
        self._max_attempts = max_attempts
        # Requests from earlier runs count against long windows, such as Tiingo's hour.
        longest = max((limit.per for limit in config.limits), default=timedelta(0))
        history = cache.fetch_times(clock() - longest) if longest > max_wait else []
        self._limiter = RateLimiter(
            config.name,
            config.limits,
            clock=clock,
            sleep=sleep,
            max_wait=max_wait,
            history=history,
        )
        self._http = httpx2.Client(
            base_url=config.base_url,
            params=params,
            headers=headers,
            transport=transport,
            timeout=30.0,
            follow_redirects=True,
        )

    def get(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> CachedResponse:
        """GET a path (relative to the source's base URL) or a full URL.

        Answers from the raw cache unless the client was made with `refresh`.
        Raises FetchError if the request fails, and RateLimitExceeded if the source's
        limits would mean a long wait.
        """
        request = self._http.build_request("GET", path, params=params)
        url = str(request.url)
        if not self.refresh and (cached := self.cache.get("GET", url)) is not None:
            return cached
        response = self._send(request)
        return self.cache.put(
            "GET",
            url,
            status_code=response.status_code,
            content=response.content,
            headers=response.headers,
            fetched_at=self._clock(),
        )

    def _send(self, request: httpx2.Request) -> httpx2.Response:
        """Send with retries. Errors are raised outside `except` blocks on purpose:
        httpx2's own messages include the full URL, credentials and all, and chaining
        them would print them in tracebacks."""
        problem = ""
        for attempt in range(1, self._max_attempts + 1):
            self._limiter.acquire()
            delay = timedelta(seconds=2 ** (attempt - 1))
            try:
                response = self._http.send(request)
            except httpx2.TransportError as error:
                problem = type(error).__name__
            else:
                content_type = response.headers.get("content-type", "")
                if response.is_success and "json" in content_type.lower():
                    return response
                problem = f"HTTP {response.status_code}"
                if response.is_success:
                    problem += (
                        f", but {content_type or 'no content type'} instead of JSON "
                        "(is the source down for maintenance?)"
                    )
                    break
                if response.status_code in (401, 403):
                    problem += " (check this source's credentials in backend/.env)"
                if response.status_code not in RETRY_STATUSES:
                    break
                delay = _retry_after(response, self._clock()) or delay
            if attempt == self._max_attempts:
                break
            if delay > self._max_wait:
                raise RateLimitExceeded(self.config.name, self._clock() + delay)
            self._sleep(delay.total_seconds())
        raise FetchError(
            self._scrub(
                f"{self.config.name}: GET {redact_url(str(request.url))} failed "
                f"after {attempt} attempt{'s' if attempt > 1 else ''}: {problem}"
            )
        )

    def _scrub(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _retry_after(response: httpx2.Response, now: datetime) -> timedelta | None:
    """How long a response's Retry-After header asks us to wait, if it says."""
    value = response.headers.get("retry-after", "").strip()
    if value.isdigit():
        return timedelta(seconds=int(value))
    try:
        when = parsedate_to_datetime(value)
    except TypeError, ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(when - now, timedelta(0))


def client_for(
    source: str, settings: Settings, *, refresh: bool = False, **options: Any
) -> SourceClient:
    """A client for `source` ("sec", "fred", or "tiingo") that caches under
    DATA_DIR/raw/<source>/ and sends the credentials in `settings`.

    `options` go to SourceClient (tests pass a fake transport and clock). Raises
    MissingSettingError if the source's key or User-Agent isn't set.
    """
    config = SOURCES.get(source)
    if config is None:
        raise ValueError(
            f"unknown source {source!r}; expected one of {sorted(SOURCES)}"
        )
    params: dict[str, str] = {}
    headers: dict[str, str] = {}
    secrets: list[str] = []
    match source:
        case "sec":
            if not settings.sec_user_agent:
                raise MissingSettingError(
                    "SEC_USER_AGENT isn't set. SEC refuses requests without a name "
                    "and contact email; see backend/.env.example."
                )
            headers["User-Agent"] = settings.sec_user_agent
        case "fred":
            key = _secret(settings.fred_api_key, "FRED_API_KEY")
            params |= {"api_key": key, "file_type": "json"}
            secrets.append(key)
        case "tiingo":
            key = _secret(settings.tiingo_api_key, "TIINGO_API_KEY")
            headers["Authorization"] = f"Token {key}"
            secrets.append(key)
    return SourceClient(
        config,
        RawCache(settings.data_dir / "raw", source),
        params=params,
        headers=headers,
        secrets=secrets,
        refresh=refresh,
        **options,
    )


def _secret(value: SecretStr | None, name: str) -> str:
    if value is None or not value.get_secret_value():
        raise MissingSettingError(f"{name} isn't set; see backend/.env.example.")
    return value.get_secret_value()
