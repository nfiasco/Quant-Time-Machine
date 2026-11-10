# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Smoke-tests a deployed API (S15.1): run it after each deploy and each store upload.

From backend/:

    uv run scripts/smoke_test.py https://quant-time-machine-api.up.railway.app
    uv run scripts/smoke_test.py URL --data-version 20261101T202624Z

Every check asks about June 5, 2020 at 09:30 ET, the acceptance example in
doc/reference/time-model.md. Point-in-time answers don't change when more data is ingested, so the
expected values hold for any store that covers 2020. The checks:

- health: /health answers ok.
- cors: the production web app's origin (--origin) may read responses.
- macro: UNRATE is May 2020's first print, 13.3%, published at 08:30 ET that morning.
- filing: Apple's latest 10-Q is the one accepted at 18:03:10 ET on April 30, 2020.
- prices: raw prices answer 403 prices_restricted, as on every public deployment (D2).

With --data-version, the macro and filing answers must also come from that data version,
which confirms a store upload landed. Exits 1 if any check fails.

Standard library only, so any Python 3.14 runs it. tests/test_smoke_test.py runs the same
checks against the fixture store, so they stay in step with the API.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

PRODUCTION_ORIGIN = "https://quant-time-machine-uy5f.vercel.app"
AS_OF = "2020-06-05"


@dataclass(frozen=True)
class Reply:
    """An HTTP response: its status, headers (names in lower case), and parsed JSON."""

    status: int
    headers: Mapping[str, str]
    body: Any


Get = Callable[[str, Mapping[str, str]], Reply]
"""Fetches a path, such as "/health", sending extra request headers."""


@dataclass(frozen=True)
class Check:
    name: str
    path: str
    verify: Callable[[Reply], str | None]
    """Returns what's wrong with the reply, or None if it's right."""
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Result:
    name: str
    path: str
    problem: str | None
    seconds: float


def http_get(base_url: str, *, timeout: float = 30) -> Get:
    """A Get for a deployed API at `base_url`."""
    base = base_url.rstrip("/")

    def get(path: str, headers: Mapping[str, str]) -> Reply:
        request = urllib.request.Request(
            base + path,
            headers={"Accept": "application/json", "User-Agent": "qtm-smoke-test"}
            | dict(headers),
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return _reply(response.status, response.headers, response.read())
        except urllib.error.HTTPError as error:
            return _reply(error.code, error.headers, error.read())

    return get


def _reply(status: int, headers: Any, raw: bytes) -> Reply:
    try:
        body = json.loads(raw) if raw else None
    except ValueError:
        body = None
    return Reply(status, {name.lower(): value for name, value in headers.items()}, body)


def _instant(text: Any) -> datetime | None:
    """A timestamp with an offset, as a UTC datetime, or None if it isn't one."""
    try:
        moment = datetime.fromisoformat(text)
    except TypeError, ValueError:
        return None
    return moment.astimezone(UTC) if moment.tzinfo else None


def _status(reply: Reply, expected: int) -> str | None:
    if reply.status != expected:
        return f"status {reply.status}, expected {expected}"
    if not isinstance(reply.body, dict):
        return "the body isn't a JSON object"
    return None


def _answer(
    reply: Reply, data_version: str | None, expected: Mapping[str, Any]
) -> str | None:
    """Checks a 200 /v1 answer: its knowledge time, data version, and `data` fields.
    Timestamps in `expected` are compared as instants."""
    if problem := _status(reply, 200):
        return problem
    knowledge_time = _instant(reply.body.get("knowledge_time"))
    if knowledge_time != datetime(2020, 6, 5, 13, 30, tzinfo=UTC):
        return f"knowledge_time is {reply.body.get('knowledge_time')!r}"
    if data_version is not None and reply.body.get("data_version") != data_version:
        return (
            f"data_version is {reply.body.get('data_version')!r}, "
            f"expected {data_version!r}"
        )
    data = reply.body.get("data")
    if not isinstance(data, dict):
        return f"no data: {reply.body.get('reason')!r}"
    for key, want in expected.items():
        got = data.get(key)
        same = _instant(got) == want if isinstance(want, datetime) else got == want
        if not same:
            return f"data.{key} is {got!r}, expected {want!r}"
    return None


def checks(origin: str, data_version: str | None) -> list[Check]:
    """The smoke test's checks, for the web app at `origin`."""

    def health(reply: Reply) -> str | None:
        if problem := _status(reply, 200):
            return problem
        return None if reply.body == {"status": "ok"} else f"body is {reply.body!r}"

    def cors(reply: Reply) -> str | None:
        allowed = reply.headers.get("access-control-allow-origin")
        if allowed != origin:
            return f"access-control-allow-origin is {allowed!r}, expected {origin!r}"
        return None

    def macro(reply: Reply) -> str | None:
        return _answer(
            reply,
            data_version,
            {
                "series_id": "UNRATE",
                "period": "2020-05-01",
                "value": 13.3,
                "available_at": datetime(2020, 6, 5, 12, 30, tzinfo=UTC),
            },
        )

    def filing(reply: Reply) -> str | None:
        return _answer(
            reply,
            data_version,
            {
                "ticker": "AAPL",
                "form": "10-Q",
                "accession_number": "0000320193-20-000052",
                "available_at": datetime(2020, 4, 30, 22, 3, 10, tzinfo=UTC),
            },
        )

    def prices(reply: Reply) -> str | None:
        if problem := _status(reply, 403):
            return problem
        code = (reply.body.get("error") or {}).get("code")
        if code != "prices_restricted":
            return f"error code is {code!r}, expected 'prices_restricted'"
        return None

    return [
        Check("health", "/health", health),
        Check("cors", "/health", cors, headers={"Origin": origin}),
        Check("macro", f"/v1/macro/UNRATE?as_of={AS_OF}", macro),
        Check("filing", f"/v1/filings/AAPL/latest?as_of={AS_OF}&form=10-Q", filing),
        Check("prices", f"/v1/prices/AAPL?as_of={AS_OF}", prices),
    ]


def run_checks(
    get: Get, *, origin: str = PRODUCTION_ORIGIN, data_version: str | None = None
) -> list[Result]:
    """Runs every check through `get`. A request that fails outright, such as a refused
    connection or a timeout, fails its check and the others still run."""
    results = []
    for check in checks(origin, data_version):
        started = time.perf_counter()
        try:
            problem = check.verify(get(check.path, check.headers))
        except OSError as error:
            problem = f"request failed: {error}"
        results.append(
            Result(check.name, check.path, problem, time.perf_counter() - started)
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("url", help="The API's base URL, such as https://….app")
    parser.add_argument(
        "--origin",
        default=PRODUCTION_ORIGIN,
        help=f"The web app origin that must pass CORS (default: {PRODUCTION_ORIGIN})",
    )
    parser.add_argument(
        "--data-version",
        help="The data version the answers must come from, such as 20261101T202624Z",
    )
    args = parser.parse_args(argv)

    results = run_checks(
        http_get(args.url), origin=args.origin, data_version=args.data_version
    )
    print(f"Smoke test of {args.url}, as of {AS_OF}")
    for result in results:
        status = "FAIL" if result.problem else "ok"
        took = f"{result.seconds * 1000:.0f} ms"
        line = f"  {status:<4}  {result.name:<7} {result.path} ({took})"
        print(f"{line}: {result.problem}" if result.problem else line)
    failed = sum(1 for result in results if result.problem)
    print(f"{len(results)} checks, {failed} failed" if failed else "All checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
