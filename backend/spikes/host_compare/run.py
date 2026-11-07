# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx==0.28.1"]
# ///
"""Times hosts running spikes/host_compare's image side by side (Railway vs Cloud Run).

Every command takes the hosts as --target NAME=URL, repeatable. A target that requires
Google sign-in (a private Cloud Run service) also gets --gcloud NAME, and its requests
carry `gcloud auth print-identity-token`. /bench routes need BENCH_TOKEN in the
environment. Results go to --out as JSON lines (default: a new temporary directory),
never into the repository, and each command prints a Markdown summary.

Run from backend/, for example:

    uv run spikes/host_compare/run.py probe   --target rw=https://... --target cr=https://... --gcloud cr
    uv run spikes/host_compare/run.py latency --target ... --rounds 100
    uv run spikes/host_compare/run.py load    --target ... --path /v1/macro/UNRATE?as_of=2020-06-05 --levels 1,10,50
    uv run spikes/host_compare/run.py bg      --target ... --seconds 60
    uv run spikes/host_compare/run.py crash   --target ...
    uv run spikes/host_compare/run.py long    --target ... --seconds 960 --mode sleep
    uv run spikes/host_compare/run.py work    --target ... --tickers 10

Commands:
    probe    one fresh-connection request to /bench/info per target, at the same moment,
             with the server's timestamps, so a cold start splits into its parts
    latency  interleaved keep-alive requests over several routes, plus fresh connections
    load     closed-loop concurrency levels against one route, per target in turn
    bg       CPU work in a thread after its request ends, sampled per second
    crash    ends the process (or, with --oom MB, exceeds its memory limit), then times
             how long until another instance answers
    watch    polls /health for --seconds, for example across a redeploy, and reports errors
    long     one long idle (sleep) or streaming request, to find the host's time limit
    work     spikes/hosting.py's backtest-shaped workload inside one request
"""

import argparse
import asyncio
import json
import os
import random
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx

DEFAULT_PATHS = [
    "/health",
    "/v1/macro/UNRATE?as_of=2020-06-05",
    "/v1/fundamentals/AAPL?as_of=2020-06-05&metric=revenue",
    "/v1/catalog/companies?as_of=2020-06-05",
    "/v1/snapshot?as_of=2020-06-05&tickers=AAPL,MSFT,JPM&series=UNRATE,FEDFUNDS",
    "/bench/cpu?units=100",
]


@dataclass
class Target:
    name: str
    url: str
    gcloud: bool = False
    _token: str | None = field(default=None, repr=False)
    _token_at: float = 0.0

    def headers(self) -> dict[str, str]:
        headers = {"user-agent": "qtm-host-compare/1.0"}
        if bench := os.environ.get("BENCH_TOKEN"):
            headers["x-bench-token"] = bench
        if self.gcloud:
            if self._token is None or time.time() - self._token_at > 40 * 60:
                self._token = subprocess.run(
                    ["gcloud", "auth", "print-identity-token"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                self._token_at = time.time()
            headers["authorization"] = f"Bearer {self._token}"
        return headers


class Recorder:
    """Appends JSON lines to one file per command run."""

    def __init__(self, out: Path, command: str) -> None:
        out.mkdir(parents=True, exist_ok=True)
        self.path = out / f"{command}-{time.strftime('%Y%m%dT%H%M%S')}.jsonl"

    def write(self, record: dict) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(record) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name)
        p.add_argument("--target", action="append", required=True, help="NAME=URL")
        p.add_argument(
            "--gcloud", action="append", default=[], help="NAME needing sign-in"
        )
        p.add_argument("--out", type=Path, default=None)
        return p

    command("probe")
    p = command("latency")
    p.add_argument("--rounds", type=int, default=100)
    p.add_argument("--fresh", type=int, default=20, help="fresh-connection requests")
    p.add_argument("--path", action="append", default=None)
    p = command("load")
    p.add_argument("--path", required=True)
    p.add_argument("--levels", default="1,10,50")
    p.add_argument("--duration", type=float, default=30.0)
    p.add_argument("--timeout", type=float, default=30.0)
    p = command("bg")
    p.add_argument("--seconds", type=float, default=60.0)
    p = command("crash")
    p.add_argument(
        "--oom", type=int, default=0, help="allocate this many MB instead of exiting"
    )
    p = command("watch")
    p.add_argument("--seconds", type=float, default=180.0)
    p.add_argument("--interval", type=float, default=0.25)
    p = command("long")
    p.add_argument("--seconds", type=float, required=True)
    p.add_argument("--mode", choices=["sleep", "stream"], default="sleep")
    p.add_argument("--every", type=float, default=30.0, help="stream: seconds per line")
    p = command("work")
    p.add_argument("--tickers", type=int, default=10)
    args = parser.parse_args()

    targets = []
    for spec in args.target:
        name, url = spec.split("=", 1)
        targets.append(Target(name, url.rstrip("/"), gcloud=name in args.gcloud))
    out = args.out or Path(tempfile.mkdtemp(prefix="host-compare-"))
    recorder = Recorder(out, args.command)
    handler = {
        "probe": cmd_probe,
        "latency": cmd_latency,
        "load": cmd_load,
        "bg": cmd_bg,
        "crash": cmd_crash,
        "watch": cmd_watch,
        "long": cmd_long,
        "work": cmd_work,
    }[args.command]
    handler(targets, args, recorder)
    print(f"\nRaw results: {recorder.path}", file=sys.stderr)


# --- probe -------------------------------------------------------------------------


def timed_request(
    client: httpx.Client, method: str, url: str, headers: dict, timeout: float = 120.0
) -> dict:
    """One request with its phases: TCP connect (with DNS), TLS, first byte, and total."""
    marks: dict[str, float] = {}

    def trace(event: str, info: dict) -> None:
        marks.setdefault(event, time.perf_counter())

    sent_epoch, started = time.time(), time.perf_counter()
    try:
        response = client.request(
            method, url, headers=headers, timeout=timeout, extensions={"trace": trace}
        )
        error = None
    except httpx.HTTPError as exc:
        response, error = None, f"{type(exc).__name__}: {exc}"
    finished = time.perf_counter()

    def since(event: str) -> float | None:
        return (marks[event] - started) * 1000 if event in marks else None

    record = {
        "sent": sent_epoch,
        "connect_ms": _delta(
            marks, "connection.connect_tcp.started", "connection.connect_tcp.complete"
        ),
        "tls_ms": _delta(
            marks, "connection.start_tls.started", "connection.start_tls.complete"
        ),
        "ttfb_ms": since("http11.receive_response_headers.complete"),
        "total_ms": (finished - started) * 1000,
        "error": error,
    }
    if response is not None:
        record.update(
            status=response.status_code,
            bytes=len(response.content),
            instance=response.headers.get("x-bench-instance"),
            count=_int(response.headers.get("x-bench-count")),
            arrived=_float(response.headers.get("x-bench-arrived")),
            app_ms=_server_timing(response.headers.get("server-timing")),
        )
        if response.headers.get("content-type", "").startswith("application/json"):
            try:
                record["body"] = response.json()
            except ValueError:
                pass
    return record


def probe_once(target: Target) -> dict:
    host = urlsplit(target.url).hostname
    dns_started = time.perf_counter()
    try:
        socket.getaddrinfo(host, 443)
        dns_ms = (time.perf_counter() - dns_started) * 1000
    except OSError:
        dns_ms = None
    headers = target.headers()
    with httpx.Client(http2=False) as client:
        record = timed_request(client, "GET", target.url + "/bench/info", headers)
    record["dns_ms"] = dns_ms
    info = record.pop("body", None) or {}
    record["target"] = target.name
    for key in (
        "instance",
        "requests",
        "container_started",
        "process_started",
        "import_started",
        "app_ready",
        "first_request",
        "kernel_booted",
        "rss_mb",
    ):
        record[f"srv_{key}"] = info.get(key)
    started = info.get("container_started")
    if started and record.get("arrived"):
        # Seconds between the container starting and our request arriving: a few
        # seconds means this request woke a new container.
        record["container_age_s"] = record["arrived"] - started
        record["cold"] = record["container_age_s"] < 60
        record["sent_to_container_s"] = started - record["sent"]
        record["container_to_ready_s"] = info["app_ready"] - started
        record["ready_to_arrived_s"] = record["arrived"] - info["app_ready"]
    return record


def cmd_probe(targets: list[Target], args, recorder: Recorder) -> None:
    async def gather() -> list[dict]:
        return await asyncio.gather(
            *(asyncio.to_thread(probe_once, t) for t in targets)
        )

    records = asyncio.run(gather())
    print(
        "| Target | Status | Cold | First byte | Connect | TLS | Container age | Start → ready | Sent → container |"
    )
    print("| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in records:
        recorder.write(r)
        print(
            f"| {r['target']} | {r.get('status', r['error'])} | {r.get('cold')} | "
            f"{_ms(r['ttfb_ms'])} | {_ms(r['connect_ms'])} | {_ms(r['tls_ms'])} | "
            f"{_s(r.get('container_age_s'))} | {_s(r.get('container_to_ready_s'))} | "
            f"{_s(r.get('sent_to_container_s'))} |"
        )


# --- latency -----------------------------------------------------------------------


def cmd_latency(targets: list[Target], args, recorder: Recorder) -> None:
    paths = args.path or DEFAULT_PATHS
    clients = {t.name: httpx.Client(http2=False) for t in targets}
    samples: dict[tuple[str, str], list[dict]] = {}
    try:
        for t in targets:  # warm up connections and instances
            for path in paths:
                for _ in range(3):
                    timed_request(clients[t.name], "GET", t.url + path, t.headers())
        for i in range(args.rounds):
            for path in paths:
                order = targets[:]
                random.shuffle(order)
                for t in order:
                    r = timed_request(clients[t.name], "GET", t.url + path, t.headers())
                    r.pop("body", None)
                    r.update(target=t.name, path=path, round=i, kind="keepalive")
                    recorder.write(r)
                    samples.setdefault((t.name, path), []).append(r)
        fresh: dict[str, list[dict]] = {}
        for i in range(args.fresh):
            order = targets[:]
            random.shuffle(order)
            for t in order:
                with httpx.Client(http2=False) as c:
                    r = timed_request(c, "GET", t.url + "/health", t.headers())
                r.pop("body", None)
                r.update(target=t.name, path="/health", round=i, kind="fresh")
                recorder.write(r)
                fresh.setdefault(t.name, []).append(r)
    finally:
        for c in clients.values():
            c.close()

    print("### Keep-alive requests (ms)\n")
    print(
        "| Route | Target | n | Errors | p50 | p90 | p99 | Mean | App p50 | Overhead p50 |"
    )
    print("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for path in paths:
        for t in targets:
            rows = samples.get((t.name, path), [])
            ok = [r for r in rows if r.get("status") == 200]
            totals = [r["total_ms"] for r in ok]
            apps = [r["app_ms"] for r in ok if r.get("app_ms") is not None]
            overhead = [
                r["ttfb_ms"] - r["app_ms"]
                for r in ok
                if r.get("app_ms") is not None and r.get("ttfb_ms")
            ]
            print(
                f"| `{path[:48]}` | {t.name} | {len(rows)} | {len(rows) - len(ok)} | "
                f"{_ms(pct(totals, 50))} | {_ms(pct(totals, 90))} | {_ms(pct(totals, 99))} | "
                f"{_ms(statistics.fmean(totals) if totals else None)} | {_ms(pct(apps, 50))} | "
                f"{_ms(pct(overhead, 50))} |"
            )
    print("\n### Fresh connections to /health (ms)\n")
    print(
        "| Target | n | Connect p50 | TLS p50 | First byte p50 | Total p50 | Total p90 |"
    )
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for t in targets:
        rows = [r for r in fresh.get(t.name, []) if r.get("status") == 200]

        def col(key: str, rows: list[dict] = rows) -> list[float]:
            return [r[key] for r in rows if r.get(key) is not None]

        print(
            f"| {t.name} | {len(rows)} | {_ms(pct(col('connect_ms'), 50))} | "
            f"{_ms(pct(col('tls_ms'), 50))} | {_ms(pct(col('ttfb_ms'), 50))} | "
            f"{_ms(pct(col('total_ms'), 50))} | {_ms(pct(col('total_ms'), 90))} |"
        )


# --- load --------------------------------------------------------------------------


async def run_level(
    target: Target, path: str, concurrency: int, duration: float, timeout: float
) -> dict:
    headers = target.headers()
    limits = httpx.Limits(
        max_connections=concurrency, max_keepalive_connections=concurrency
    )
    latencies: list[float] = []
    statuses: dict[str, int] = {}
    instances: dict[str, int] = {}
    timeline: list[tuple[float, float, str | None]] = []
    async with httpx.AsyncClient(limits=limits, timeout=timeout, http2=False) as client:
        started = time.perf_counter()
        deadline = started + duration

        async def worker() -> None:
            while time.perf_counter() < deadline:
                t0 = time.perf_counter()
                try:
                    response = await client.get(target.url + path, headers=headers)
                    key = str(response.status_code)
                    instance = response.headers.get("x-bench-instance")
                except httpx.HTTPError as exc:
                    key, instance = type(exc).__name__, None
                t1 = time.perf_counter()
                statuses[key] = statuses.get(key, 0) + 1
                if key == "200":
                    latencies.append((t1 - t0) * 1000)
                if instance:
                    instances[instance] = instances.get(instance, 0) + 1
                timeline.append((t1 - started, (t1 - t0) * 1000, instance))

        await asyncio.gather(*(worker() for _ in range(concurrency)))
        elapsed = time.perf_counter() - started
    ok = len(latencies)
    # Throughput and instance count per 5-second window, to see scaling happen.
    windows = []
    for start in range(0, int(duration) + 5, 5):
        rows = [r for r in timeline if start <= r[0] < start + 5]
        if rows:
            windows.append(
                {
                    "t": start,
                    "rps": len(rows) / 5,
                    "p50": pct([r[1] for r in rows], 50),
                    "instances": len({r[2] for r in rows if r[2]}),
                }
            )
    return {
        "target": target.name,
        "path": path,
        "concurrency": concurrency,
        "seconds": elapsed,
        "requests": sum(statuses.values()),
        "ok": ok,
        "rps": ok / elapsed,
        "statuses": statuses,
        "instances": instances,
        "p50": pct(latencies, 50),
        "p90": pct(latencies, 90),
        "p99": pct(latencies, 99),
        "max": max(latencies) if latencies else None,
        "windows": windows,
    }


def cmd_load(targets: list[Target], args, recorder: Recorder) -> None:
    levels = [int(x) for x in args.levels.split(",")]
    results = []
    for level in levels:
        for t in targets:
            r = asyncio.run(run_level(t, args.path, level, args.duration, args.timeout))
            recorder.write(r)
            results.append(r)
            print(
                f"  {t.name} c={level}: {r['rps']:.1f} req/s, p50 {_ms(r['p50'])} ms, "
                f"p99 {_ms(r['p99'])} ms, {len(r['instances'])} instance(s), {r['statuses']}",
                file=sys.stderr,
            )
            time.sleep(3)
    print(f"### Load on `{args.path}` ({args.duration:.0f} s per level)\n")
    print(
        "| Concurrency | Target | Req/s | p50 ms | p90 ms | p99 ms | Errors | Instances |"
    )
    print("| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in results:
        errors = r["requests"] - r["ok"]
        print(
            f"| {r['concurrency']} | {r['target']} | {r['rps']:.1f} | {_ms(r['p50'])} | "
            f"{_ms(r['p90'])} | {_ms(r['p99'])} | {errors} | {len(r['instances'])} |"
        )


# --- bg ----------------------------------------------------------------------------


def cmd_bg(targets: list[Target], args, recorder: Recorder) -> None:
    """Starts the job on every target, waits with no requests in flight, then reads it."""
    with httpx.Client(timeout=60) as client:
        baseline = {}
        for t in targets:
            rates = [
                client.get(t.url + "/bench/cpu?units=100", headers=t.headers()).json()[
                    "units_per_s"
                ]
                for _ in range(5)
            ]
            baseline[t.name] = statistics.median(rates)
        jobs = {}
        for t in targets:
            r = client.post(
                t.url + f"/bench/bg?seconds={args.seconds}", headers=t.headers()
            )
            r.raise_for_status()
            jobs[t.name] = r.json()
        time.sleep(args.seconds + 5)
        print(f"### CPU after the response ({args.seconds:.0f} s background job)\n")
        print(
            "| Target | Full-speed units/s | Background units/s | Share of full speed |"
        )
        print("| --- | ---: | ---: | ---: |")
        for t in targets:
            job = jobs[t.name]
            status = None
            for _ in range(
                10
            ):  # another instance may answer; retry until the job's does
                r = client.get(t.url + f"/bench/bg/{job['job']}", headers=t.headers())
                if r.status_code == 200:
                    status = r.json()
                    break
            record = {
                "target": t.name,
                "baseline_units_per_s": baseline[t.name],
                "start": job,
                "status": status,
            }
            recorder.write(record)
            if status is None:
                print(f"| {t.name} | {baseline[t.name]:.0f} | job not found | |")
                continue
            per_second = status["per_second"]
            # Leave out the first second, which overlaps the request that started it.
            body = per_second[1:] or per_second
            rate = statistics.fmean(body) if body else 0.0
            print(
                f"| {t.name} | {baseline[t.name]:.0f} | {rate:.0f} | {rate / baseline[t.name]:.1%} |"
            )


# --- crash -------------------------------------------------------------------------


def cmd_crash(targets: list[Target], args, recorder: Recorder) -> None:
    """Ends the process (or, with --oom MB, makes it exceed its memory limit)."""
    print(
        "| Target | How | Trigger response | Recovery (s) | Failed polls | Errors seen | New instance's container age (s) |"
    )
    print("| --- | --- | --- | ---: | ---: | --- | ---: |")
    for t in targets:
        with httpx.Client(timeout=60) as client:
            before = client.get(t.url + "/bench/info", headers=t.headers()).json()[
                "instance"
            ]
            try:
                if args.oom:
                    r = client.post(
                        t.url + f"/bench/mem?mb={args.oom}&hold=2", headers=t.headers()
                    )
                else:
                    r = client.post(t.url + "/bench/crash", headers=t.headers())
                trigger = f"{r.status_code} {r.text[:60]}"
            except httpx.HTTPError as exc:
                trigger = type(exc).__name__
        crashed = time.perf_counter()
        failures, errors, after = 0, {}, None
        while time.perf_counter() - crashed < 300:
            try:
                with httpx.Client(timeout=15) as client:
                    r = client.get(t.url + "/bench/info", headers=t.headers())
                if r.status_code == 200 and r.json()["instance"] != before:
                    after = r.json()
                    break
                key = str(r.status_code) if r.status_code != 200 else "old instance"
            except httpx.HTTPError as exc:
                key = type(exc).__name__
            failures += 1
            errors[key] = errors.get(key, 0) + 1
            time.sleep(0.5)
        recovery = time.perf_counter() - crashed
        age = (
            (after["now"] - after["container_started"])
            if after and after.get("container_started")
            else None
        )
        how = f"oom {args.oom} MB" if args.oom else "exit(1)"
        record = {
            "target": t.name,
            "how": how,
            "trigger": trigger,
            "before": before,
            "after": after and after["instance"],
            "recovery_s": recovery,
            "failed_polls": failures,
            "errors": errors,
            "container_age_s": age,
        }
        recorder.write(record)
        print(
            f"| {t.name} | {how} | {trigger} | {recovery:.1f} | {failures} | {errors} | {_s(age)} |"
        )


# --- watch -------------------------------------------------------------------------


def cmd_watch(targets: list[Target], args, recorder: Recorder) -> None:
    """Polls /health on every target for --seconds (say, across a redeploy) and reports
    errors, the longest stretch without a 200, and when a new instance took over."""

    def one(t: Target) -> dict:
        polls, instances = [], []
        deadline = time.perf_counter() + args.seconds
        with httpx.Client(timeout=10) as client:
            while time.perf_counter() < deadline:
                at = time.time()
                try:
                    r = client.get(t.url + "/health", headers=t.headers())
                    status, instance = r.status_code, r.headers.get("x-bench-instance")
                except httpx.HTTPError as exc:
                    status, instance = type(exc).__name__, None
                polls.append((at, status, instance))
                if instance and (not instances or instances[-1][1] != instance):
                    instances.append((at, instance))
                time.sleep(args.interval)
        worst = gap_start = 0.0
        for at, status, _ in polls:
            if status != 200:
                gap_start = gap_start or at
                worst = max(worst, at - gap_start)
            else:
                gap_start = 0.0
        errors: dict[str, int] = {}
        for _, status, _ in polls:
            if status != 200:
                errors[str(status)] = errors.get(str(status), 0) + 1
        return {
            "target": t.name,
            "polls": len(polls),
            "errors": errors,
            "longest_error_stretch_s": worst,
            "instances": instances,
        }

    async def gather() -> list[dict]:
        return await asyncio.gather(*(asyncio.to_thread(one, t) for t in targets))

    print("| Target | Polls | Errors | Longest error stretch (s) | Instance switches |")
    print("| --- | ---: | --- | ---: | ---: |")
    for r in asyncio.run(gather()):
        recorder.write(r)
        print(
            f"| {r['target']} | {r['polls']} | {r['errors'] or 'none'} | "
            f"{r['longest_error_stretch_s']:.1f} | {max(0, len(r['instances']) - 1)} |"
        )


# --- long --------------------------------------------------------------------------


def cmd_long(targets: list[Target], args, recorder: Recorder) -> None:
    """One long request per target, all at once; reports when and how each ended."""

    def one(t: Target) -> dict:
        if args.mode == "sleep":
            path = f"/bench/sleep?seconds={args.seconds}"
        else:
            path = f"/bench/stream?seconds={args.seconds}&every={args.every}"
        started = time.perf_counter()
        received, last_line, status, error = 0, None, None, None
        # TCP keepalives every 30 s keep a home router from dropping the idle connection,
        # so whatever ends the request is the host, not the network in between.
        idle_option = getattr(
            socket, "TCP_KEEPIDLE", getattr(socket, "TCP_KEEPALIVE", None)
        )
        options = [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
        if idle_option is not None:
            options.append((socket.IPPROTO_TCP, idle_option, 30))
        transport = httpx.HTTPTransport(socket_options=options)
        timeout = httpx.Timeout(args.seconds + 600, connect=30)
        try:
            with (
                httpx.Client(transport=transport, timeout=timeout) as client,
                client.stream("GET", t.url + path, headers=t.headers()) as r,
            ):
                status = r.status_code
                for line in r.iter_lines():
                    received += 1
                    last_line = line
        except httpx.HTTPError as exc:
            error = f"{type(exc).__name__}: {exc}"
        return {
            "target": t.name,
            "mode": args.mode,
            "asked_s": args.seconds,
            "ended_after_s": time.perf_counter() - started,
            "status": status,
            "lines": received,
            "last_line": last_line,
            "error": error,
        }

    async def gather() -> list[dict]:
        return await asyncio.gather(*(asyncio.to_thread(one, t) for t in targets))

    print(
        "| Target | Mode | Asked (s) | Ended after (s) | Status | Last line | Error |"
    )
    print("| --- | --- | ---: | ---: | --- | --- | --- |")
    for r in asyncio.run(gather()):
        recorder.write(r)
        print(
            f"| {r['target']} | {r['mode']} | {r['asked_s']:.0f} | {r['ended_after_s']:.1f} | "
            f"{r['status']} | {str(r['last_line'])[:40]} | {r['error'] or ''} |"
        )


# --- work --------------------------------------------------------------------------


def cmd_work(targets: list[Target], args, recorder: Recorder) -> None:
    print("| Target | Tickers | Wall (s) | CPU (s) | Peak memory (MB) |")
    print("| --- | ---: | ---: | ---: | ---: |")
    with httpx.Client(timeout=3600) as client:
        for t in targets:
            r = client.get(
                t.url + f"/bench/work?tickers={args.tickers}", headers=t.headers()
            )
            r.raise_for_status()
            body = r.json()
            recorder.write({"target": t.name, "tickers": args.tickers, **body})
            print(
                f"| {t.name} | {args.tickers} | {body['seconds']:.1f} | {body['cpu_seconds']:.1f} | "
                f"{body['peak_rss_mb']:.0f} |"
            )


# --- helpers -----------------------------------------------------------------------


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _delta(marks: dict, start: str, end: str) -> float | None:
    if start in marks and end in marks:
        return (marks[end] - marks[start]) * 1000
    return None


def _server_timing(header: str | None) -> float | None:
    if not header:
        return None
    for part in header.split(","):
        if part.strip().startswith("app;dur="):
            return float(part.strip()[len("app;dur=") :])
    return None


def _int(value: str | None) -> int | None:
    return int(value) if value else None


def _float(value: str | None) -> float | None:
    return float(value) if value else None


def _ms(value: float | None) -> str:
    return "" if value is None else f"{value:.0f}" if value >= 100 else f"{value:.1f}"


def _s(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


if __name__ == "__main__":
    main()
