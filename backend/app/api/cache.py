"""A cache of as-of answers (S8.6; the contract is doc/reference/api-v1.md, "Caching").

An as-of answer never changes for a given data version: a view pinned to one reads only
the files its manifest lists, and only rows ingested by then (app/data/versions.py). So
the API keeps each answer in memory, under the request's path, its other query
parameters, its knowledge time, and the data version it read, and answers a repeat
without opening a view or reading the store.

- **The key.** `as_of` counts as the instant it means, so `2020-06-05` and
  `2020-06-05T09:30` share one answer. The other parameters count as sent, so
  `tickers=aapl` and `tickers=AAPL` are kept apart, which costs only a miss.
- **One data version.** Every request reads the store's newest data version, so the
  cache holds that version's answers and starts over when another one is newest, after
  an ingestion run or a store upload. A store without a data version can change under
  the API, so nothing is cached then.
- **Only answers.** Only the 200s a route returns are kept. Errors are cheap, so they're
  answered afresh. So is a 200 that an exception handler builds, such as errors.py's
  "not known yet" answer to a LookAheadError, which no route raises today.
- **Not who asks.** The key leaves out the request's headers, since no answer depends on
  them. If sign-in (E16) makes one depend on the user, the key must name the user too.
- **HTTP.** A cached answer carries an ETag, a hash of its body, and
  `Cache-Control: no-cache`: a browser or proxy may keep it, but must check it first,
  since the next data version can change the answer at the same URL. A request whose
  `If-None-Match` names the ETag gets a 304 without a body. `Cache-Status` (RFC 9211)
  says whether the answer came from the cache.

A router opts in with `APIRouter(route_class=AsOfRoute)`. Every /v1 router does except
the backtests', whose answers change while a run goes. A route without `as_of`, such as
`/v1/catalog/signals`, isn't cached.
"""

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

from fastapi import Request, Response
from fastapi.routing import APIRoute

from app.config import Settings
from app.data.store import store_dir
from app.data.timeutil import KnowledgeTimeError, parse_knowledge_time
from app.data.versions import latest_data_version

CACHE_NAME = "qtm-api"
"""How this cache names itself in `Cache-Status`."""

type Key = tuple[str, str, tuple[tuple[str, str], ...]]
"""A request's path, its knowledge time in UTC, and its other query parameters."""


@dataclass(frozen=True)
class Answer:
    """A 200 as the cache keeps it."""

    body: bytes
    media_type: str
    etag: str
    """A hash of the body, quoted: `"3f0c…"`."""

    @classmethod
    def of(cls, body: bytes, media_type: str) -> Self:
        return cls(body, media_type, f'"{hashlib.sha256(body).hexdigest()[:32]}"')


class ResponseCache:
    """The answers of one data version, up to `max_bytes` of bodies in all.

    When it's full, the answers used longest ago go first. Safe to use from any thread.
    """

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self._data_version: str | None = None
        self._answers: OrderedDict[Key, Answer] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._answers)

    @property
    def bytes(self) -> int:
        """The size of the bodies kept."""
        return self._bytes

    def get(self, data_version: str, key: Key) -> Answer | None:
        """The answer kept for `key`, if any. Asking for another data version than the
        one the cache holds starts it over, holding that one."""
        with self._lock:
            if data_version != self._data_version:
                self._answers.clear()
                self._bytes = 0
                self._data_version = data_version
                return None
            answer = self._answers.get(key)
            if answer is not None:
                self._answers.move_to_end(key)
            return answer

    def put(self, data_version: str, key: Key, answer: Answer) -> bool:
        """Keep `answer` for `key`, and say whether it was kept. It isn't when it's
        for another data version than the cache holds, as when a newer version
        appeared while it was built, or when it's bigger than the whole cache."""
        size = len(answer.body)
        with self._lock:
            if data_version != self._data_version or size > self.max_bytes:
                return False
            replaced = self._answers.pop(key, None)
            if replaced is not None:
                self._bytes -= len(replaced.body)
            self._answers[key] = answer
            self._bytes += size
            while self._bytes > self.max_bytes:
                _, evicted = self._answers.popitem(last=False)
                self._bytes -= len(evicted.body)
            return True


class AsOfRoute(APIRoute):
    """A route whose answers are as of a knowledge time, so the app caches them.

    The cache sits in front of FastAPI's own handler, so a repeat skips the request's
    dependencies too: the view isn't opened, and the store isn't read.
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        # FastAPI may call this for each request (an included route's context lives in
        # a context variable), so the handler below keeps no state of its own.
        handle = super().get_route_handler()

        async def handle_with_cache(request: Request) -> Response:
            cache: ResponseCache | None = getattr(
                request.app.state, "response_cache", None
            )
            as_of = request.query_params.get("as_of")
            if cache is None or request.method != "GET" or as_of is None:
                return await handle(request)
            try:
                knowledge_time = parse_knowledge_time(as_of)
            except KnowledgeTimeError:
                return await handle(request)  # which answers 422
            settings: Settings = request.app.state.settings
            store = store_dir(settings.data_dir)
            data_version = latest_data_version(store)
            if data_version is None:
                return await handle(request)

            key = _key(request, knowledge_time)
            answer = cache.get(data_version, key)
            status = "hit"
            if answer is None:
                # The request reads this data version, even if a newer one appears
                # meanwhile (`newest_data_version` in conventions.py), so the answer is
                # the one for its key.
                request.state.data_version = data_version
                response = await handle(request)
                body = getattr(response, "body", None)
                if response.status_code != 200 or not isinstance(body, bytes):
                    return response
                answer = Answer.of(body, response.media_type or "application/json")
                stored = cache.put(data_version, key, answer)
                status = "fwd=miss; stored" if stored else "fwd=miss"
            return _respond(request, answer, status)

        return handle_with_cache


def _key(request: Request, knowledge_time: datetime) -> Key:
    # Sorted by name only: the sort is stable, so a repeated parameter's values keep
    # their order, and the API reads the last one.
    others = sorted(
        (
            (name, value)
            for name, value in request.query_params.multi_items()
            if name != "as_of"
        ),
        key=lambda item: item[0],
    )
    return request.url.path, knowledge_time.isoformat(), tuple(others)


def _respond(request: Request, answer: Answer, status: str) -> Response:
    headers = {
        "ETag": answer.etag,
        "Cache-Control": "no-cache",
        "Cache-Status": f"{CACHE_NAME}; {status}",
    }
    if _names(request.headers.get("if-none-match"), answer.etag):
        # Returned, not raised: errors.py would turn an HTTPException into a JSON body.
        return Response(status_code=304, headers=headers)
    return Response(answer.body, media_type=answer.media_type, headers=headers)


def _names(if_none_match: str | None, etag: str) -> bool:
    """Whether an If-None-Match header names `etag`, compared weakly as RFC 9110
    says: `W/"…"` names it too, and so does `*`."""
    if if_none_match is None:
        return False
    tags = {tag.strip().removeprefix("W/") for tag in if_none_match.split(",")}
    return "*" in tags or etag in tags
