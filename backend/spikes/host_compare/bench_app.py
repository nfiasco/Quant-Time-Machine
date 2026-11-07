"""The real API plus /bench diagnostics, so two hosts can be timed running identical code.

The image built from this folder's Dockerfile serves this module instead of app.main.
Every /health and /v1 route is the real one; /bench adds what run.py needs:

- GET  /bench/info    which instance answered, when its container and app started,
                      and what CPU, memory, and DuckDB threads it sees.
- GET  /bench/cpu     a fixed amount of pure-Python work, timed in wall and CPU time.
- GET  /bench/work    spikes/hosting.py's backtest-shaped workload, inside a request.
- GET  /bench/sleep   an idle request that answers after `seconds`.
- GET  /bench/stream  a response that sends a line every `every` seconds.
- POST /bench/bg      CPU work in a thread that outlives its request, and
  GET  /bench/bg/{id} how much of it ran in each second.
- POST /bench/crash   ends the process just after answering.
- POST /bench/mem     allocates and touches `mb` MB of memory.

Everything but /bench/info needs the X-Bench-Token header to match BENCH_TOKEN, so a
stranger who finds the URL can't crash the service or run up its bill. Never deploy this
for real users.
"""

import time

IMPORT_STARTED = time.time()

import argparse
import asyncio
import contextlib
import io
import os
import platform
import resource
import secrets
import sys
import threading
import uuid
from pathlib import Path

import duckdb
from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app import main as _main

app = _main.app
APP_READY = time.time()
INSTANCE = uuid.uuid4().hex[:10]
TOKEN = os.environ.get("BENCH_TOKEN", "")
# The Dockerfile's shell records this just before it starts Python.
CONTAINER_STARTED = float(os.environ.get("BENCH_CONTAINER_STARTED") or 0) or None
ENV_SHOWN = (
    "K_SERVICE",
    "K_REVISION",
    "CLOUD_RUN_EXECUTION",
    "PORT",
    "RAILWAY_SERVICE_NAME",
    "RAILWAY_REPLICA_ID",
    "RAILWAY_REPLICA_REGION",
    "RAILWAY_DEPLOYMENT_ID",
)

_state = {"requests": 0, "first_request": None}
_jobs: dict[str, dict] = {}


def require_token(x_bench_token: str = Header(default="")) -> None:
    if not TOKEN or not secrets.compare_digest(x_bench_token, TOKEN):
        raise HTTPException(status_code=403, detail="X-Bench-Token required")


guarded = [Depends(require_token)]


@app.middleware("http")
async def bench_headers(request: Request, call_next):
    """Tags every response with its instance, its request count, and the app's time."""
    arrived = time.time()
    _state["requests"] += 1
    count = _state["requests"]
    if _state["first_request"] is None:
        _state["first_request"] = arrived
    started = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - started) * 1000
    response.headers["x-bench-instance"] = INSTANCE
    response.headers["x-bench-count"] = str(count)
    response.headers["x-bench-arrived"] = f"{arrived:.3f}"
    response.headers["server-timing"] = f"app;dur={duration:.2f}"
    return response


@app.get("/bench/info", include_in_schema=False)
def info() -> dict:
    uptime = _read_float("/proc/uptime")
    booted = time.time() - uptime if uptime is not None else None
    return {
        "instance": INSTANCE,
        "pid": os.getpid(),
        "requests": _state["requests"],
        "now": time.time(),
        "container_started": CONTAINER_STARTED,
        "process_started": _process_started(booted),
        "import_started": IMPORT_STARTED,
        "app_ready": APP_READY,
        "first_request": _state["first_request"],
        "kernel_booted": booted,
        "cpu_count": os.cpu_count(),
        "cpu_affinity": len(os.sched_getaffinity(0))
        if hasattr(os, "sched_getaffinity")
        else None,
        "cpu_model": _cpu_model(),
        "cpu_max": _read_text("/sys/fs/cgroup/cpu.max"),
        "cpu_stat": _read_text("/sys/fs/cgroup/cpu.stat"),
        "memory_max": _read_text("/sys/fs/cgroup/memory.max"),
        "memory_total_mb": _meminfo_mb("MemTotal"),
        "rss_mb": _status_mb("VmRSS"),
        "peak_rss_mb": _peak_rss_mb(),
        "loadavg": os.getloadavg(),
        "duckdb_threads": duckdb.connect()
        .execute("SELECT current_setting('threads')")
        .fetchone()[0],
        "kernel": platform.release(),
        "python": sys.version.split()[0],
        "duckdb": duckdb.__version__,
        "env": {name: os.environ[name] for name in ENV_SHOWN if name in os.environ},
    }


def work_units(units: int) -> None:
    """Pure-Python work that holds the GIL: one unit is 10,000 loop iterations."""
    total = 0
    for _ in range(units):
        for i in range(10_000):
            total += i * i % 7


@app.get("/bench/cpu", include_in_schema=False, dependencies=guarded)
def cpu(units: int = 100) -> dict:
    wall, cpu_time = time.perf_counter(), time.thread_time()
    work_units(units)
    wall, cpu_time = time.perf_counter() - wall, time.thread_time() - cpu_time
    return {
        "instance": INSTANCE,
        "units": units,
        "wall_ms": wall * 1000,
        "cpu_ms": cpu_time * 1000,
        "units_per_s": units / wall,
    }


@app.get("/bench/work", include_in_schema=False, dependencies=guarded)
def work(
    tickers: int = 10, start: int = 2010, end: int = 2025, lookback: int = 252
) -> dict:
    """spikes/hosting.py's workload: monthly PointInTimeViews reading N tickers each."""
    from app.config import get_settings
    from app.data.store import store_dir
    from spikes import hosting

    args = argparse.Namespace(tickers=tickers, start=start, end=end, lookback=lookback)
    report = io.StringIO()
    wall, cpu_time = time.perf_counter(), time.process_time()
    with contextlib.redirect_stdout(report):
        hosting.report_workload(store_dir(get_settings().data_dir), args)
    return {
        "instance": INSTANCE,
        "seconds": time.perf_counter() - wall,
        "cpu_seconds": time.process_time() - cpu_time,
        "peak_rss_mb": _peak_rss_mb(),
        "report": report.getvalue(),
    }


@app.get("/bench/sleep", include_in_schema=False, dependencies=guarded)
async def sleep(seconds: float = 1.0) -> dict:
    started = time.time()
    await asyncio.sleep(seconds)
    return {"instance": INSTANCE, "slept": time.time() - started}


@app.get("/bench/stream", include_in_schema=False, dependencies=guarded)
async def stream(seconds: float = 10.0, every: float = 1.0) -> StreamingResponse:
    async def lines():
        started = time.time()
        while (elapsed := time.time() - started) < seconds:
            yield f"{elapsed:.1f}\n".encode()
            await asyncio.sleep(every)
        yield f"done {time.time() - started:.1f}\n".encode()

    return StreamingResponse(lines(), media_type="text/plain")


@app.post("/bench/bg", include_in_schema=False, dependencies=guarded)
def background(seconds: float = 60.0) -> dict:
    """Starts CPU work that keeps going after this response, as S8.4's runs would."""
    job_id = uuid.uuid4().hex[:8]
    job = {"started": time.time(), "seconds": seconds, "per_second": [], "done": None}
    _jobs[job_id] = job
    threading.Thread(target=_spin, args=(job,), daemon=True).start()
    return {"instance": INSTANCE, "job": job_id}


@app.get("/bench/bg/{job_id}", include_in_schema=False, dependencies=guarded)
def background_status(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="no such job on this instance")
    return {"instance": INSTANCE, "now": time.time(), **job}


@app.post("/bench/crash", include_in_schema=False, dependencies=guarded)
def crash(delay: float = 0.2) -> dict:
    threading.Timer(delay, os._exit, args=(1,)).start()
    return {"instance": INSTANCE, "exiting_in": delay}


@app.post("/bench/mem", include_in_schema=False, dependencies=guarded)
def memory(mb: int = 100, hold: float = 1.0) -> dict:
    block = bytearray(mb * 1024 * 1024)
    for i in range(0, len(block), 4096):
        block[i] = 1
    time.sleep(hold)
    rss = _status_mb("VmRSS")
    del block
    return {"instance": INSTANCE, "allocated_mb": mb, "rss_mb": rss}


def _spin(job: dict) -> None:
    started, buckets = job["started"], job["per_second"]
    while (now := time.time()) < started + job["seconds"]:
        second = int(now - started)
        while len(buckets) <= second:
            buckets.append(0)
        work_units(1)
        buckets[second] += 1
    job["done"] = time.time()


def _process_started(booted: float | None) -> float | None:
    """When this process started, from /proc (10 ms resolution)."""
    try:
        fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
        return booted + int(fields[19]) / os.sysconf("SC_CLK_TCK")
    except OSError, IndexError, ValueError, TypeError:
        return None


def _read_text(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _read_float(path: str) -> float | None:
    text = _read_text(path)
    return float(text.split()[0]) if text else None


def _cpu_model() -> str | None:
    text = _read_text("/proc/cpuinfo") or ""
    for line in text.splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return None


def _meminfo_mb(key: str) -> float | None:
    for line in (_read_text("/proc/meminfo") or "").splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1]) / 1024
    return None


def _status_mb(key: str) -> float | None:
    for line in (_read_text("/proc/self/status") or "").splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1]) / 1024
    return None


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports kibibytes.
    return peak / 1e6 if sys.platform == "darwin" else peak / 1024
