"""Runs in the background, and their status (S8.4; doc/reference/runs.md).

A whole canonical run takes over three minutes, so the API doesn't make a request wait
for one. `POST /v1/backtests` hands the spec to the app's `RunQueue`, which answers at
once with the run's ID, and a page polls `GET /v1/backtests/{id}` for its status.

- **A job** is a submitted run: its spec, the data version it's pinned to, its status,
  and when it was submitted, started, and finished. It's a file,
  DATA_DIR/runs/_jobs/<run ID>.json, beside the runs' own folders. A run's record has
  no clock in it, so two runs of the same inputs give the same bytes
  (app/backtest/records.py), and the job file is where the times go until the run
  registry replaces it (S13.1).
- **`execute(run_id, settings)`** runs one job: a plain function that reads the job's
  file, runs its spec (`run_backtest` in app/runs.py), and writes how it ended. The
  queue calls it from a thread now. A task queue could call it the same way later
  (doc/reference/hosting.md).
- **One run at a time.** The queue has one worker thread, and at most MAX_WAITING runs
  wait behind the one it's running. A run peaks at about 340 MB and uses a whole CPU,
  and nobody signs in to start one yet, so this bounds the memory and the bill.
- **A saved run has succeeded,** whatever its job file says and even without one, so a
  run saved by `python -m app.runs` is served too. The run's ID names its inputs, so
  submitting a saved run again answers with it, and runs nothing.
- **A restart stops the run in progress.** The worker is a thread in the API's
  process, which a redeploy stops. `RunQueue.recover()`, called as the server starts,
  marks every job still queued or running as failed, so a page that's polling one
  finds out. Submitting it again runs it.

The queue assumes it's the only process that runs jobs in its folder, which holds for
one server (Railway runs one replica, because of the volume).
"""

import json
import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any, Literal

from app.backtest import ENGINE_VERSION
from app.backtest.audit import timestamp
from app.backtest.records import MANIFEST, run_id
from app.backtest.schedule import ScheduleError
from app.backtest.spec import ExperimentSpec, SpecError, parse_spec
from app.config import Settings
from app.data.errors import DataVersionError
from app.data.store import store_dir
from app.data.versions import latest_data_version
from app.runs import read_document, run_backtest, runs_dir, saved_run

logger = logging.getLogger(__name__)

JOBS = "_jobs"
"""The folder of job files in DATA_DIR/runs. A run's folder is named by 64 hex digits,
so it never clashes with one."""

MAX_WAITING = 5
"""How many runs can wait behind the one that's running. At about 200 seconds for a
whole canonical run, the last of them starts within twenty minutes."""

RunStatus = Literal["queued", "running", "succeeded", "failed"]

RESTARTED = "The server restarted before this run finished. Submit it again."

BROKE = (
    "The run stopped because of a problem on our side. Submit it again, and tell the "
    "team if it keeps happening."
)

BUSY = (
    "The server is busy with other runs, and its queue is full. Try again in a few "
    "minutes."
)

CANT_SAVE = "This server can't save runs right now, so it can't start one."


class RunsUnavailableError(Exception):
    """The queue can't take a run now. Its message is a sentence a page can show."""


@dataclass(frozen=True)
class Progress:
    """How far a running job has come."""

    decisions_done: int
    decisions_total: int


@dataclass(frozen=True)
class Job:
    """A submitted run, and how far it has come."""

    run_id: str
    status: RunStatus
    spec: ExperimentSpec
    data_version: str
    engine_version: str
    submitted_at: datetime | None
    """None for a run nobody submitted here: one saved by `python -m app.runs`."""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    """Why it failed, as a sentence a page can show."""
    progress: Progress | None = None
    """Only while it's running, and only in the process that runs it: it isn't in the
    job's file."""


Runner = Callable[..., Any]
"""What runs a job's spec: `run_backtest`, unless a test passes its own."""


def jobs_dir(settings: Settings) -> Path:
    return runs_dir(settings.data_dir) / JOBS


def write_job(job: Job, settings: Settings) -> None:
    """Save a job's file, whole or not at all: written beside it, then moved."""
    folder = jobs_dir(settings)
    folder.mkdir(parents=True, exist_ok=True)
    document = {
        "run_id": job.run_id,
        "status": job.status,
        "spec": job.spec.model_dump(mode="json"),
        "data_version": job.data_version,
        "engine_version": job.engine_version,
        "submitted_at": _written(job.submitted_at),
        "started_at": _written(job.started_at),
        "finished_at": _written(job.finished_at),
        "error": job.error,
    }
    # Named by its thread too: a request and the worker can write the same job.
    partial_file = folder / f".{job.run_id}.{threading.get_ident()}.tmp"
    try:
        partial_file.write_text(json.dumps(document, indent=2), encoding="utf-8")
        partial_file.replace(folder / f"{job.run_id}.json")
    finally:
        partial_file.unlink(missing_ok=True)


def read_job(run_id: str, settings: Settings) -> Job | None:
    """A job's file, or None if there's none, or it can't be read as one."""
    return _read(jobs_dir(settings) / f"{run_id}.json")


def execute(
    run_id: str,
    settings: Settings,
    *,
    on_decision: Callable[[int, int], None] | None = None,
    run: Runner = run_backtest,
    clock: Callable[[], datetime] | None = None,
) -> Job:
    """Run a job's spec and save its record, and write how it ended to its file.

    It never raises for a run that fails: the job says why, as a sentence. A spec the
    engine refuses says what's wrong with it. Anything else is our problem, so the
    job says only that, and the log has the rest. Raises LookupError if there's no
    such job.
    """
    now = clock or _now
    job = read_job(run_id, settings)
    if job is None:
        raise LookupError(f"there's no job for run {run_id}")
    job = replace(job, status="running", started_at=now(), finished_at=None, error=None)
    write_job(job, settings)
    try:
        run(
            job.spec,
            settings,
            data_version=job.data_version,
            on_decision=on_decision,
        )
    except SpecError as error:
        job = replace(job, status="failed", error=str(error))
    except ScheduleError as error:
        job = replace(job, status="failed", error=schedule_problem(error))
    except Exception:
        logger.exception("Run %s failed", run_id)
        job = replace(job, status="failed", error=BROKE)
    else:
        job = replace(job, status="succeeded")
    job = replace(job, finished_at=now())
    write_job(job, settings)
    return job


def schedule_problem(error: ScheduleError) -> str:
    """A ScheduleError as a sentence about the spec's `schedule`."""
    return f"schedule can't be run: {str(error).rstrip('.')}."


class RunQueue:
    """The app's runs: the one in progress, the ones waiting, and every one saved."""

    def __init__(
        self,
        settings: Settings,
        *,
        run: Runner = run_backtest,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._run = run
        self._clock = clock or _now
        self._lock = threading.Lock()
        self._waiting: queue.Queue[str | None] = queue.Queue()
        self._alive: set[str] = set()  # queued or running, in this process
        self._progress: dict[str, Progress] = {}
        self._worker: threading.Thread | None = None
        self._closed = False

    def submit(self, spec: ExperimentSpec) -> Job:
        """Queue `spec` to run on the store's newest data version, and return its job.

        A run that's already saved, queued, or running isn't queued again: the same
        spec, data version, and engine version are the same run. Raises
        DataVersionError if the store has no data version yet, and
        RunsUnavailableError if the queue is full or the job can't be saved.
        """
        store = store_dir(self._settings.data_dir)
        data_version = latest_data_version(store)
        if data_version is None:
            raise DataVersionError(
                f"The store in {store} has no data version yet, and a run must be "
                "pinned to one: ingest a source first (python -m app.data.ingest)"
            )
        identifier = run_id(spec, data_version)
        with self._lock:
            found = self._find(identifier)
            if found is not None and (
                found.status == "succeeded" or identifier in self._alive
            ):
                return found
            if self._closed:
                raise RunsUnavailableError(CANT_SAVE)
            if len(self._alive) > MAX_WAITING:  # the one running, and those waiting
                raise RunsUnavailableError(BUSY)
            job = Job(
                run_id=identifier,
                status="queued",
                spec=spec,
                data_version=data_version,
                engine_version=ENGINE_VERSION,
                submitted_at=self._clock(),
            )
            try:
                write_job(job, self._settings)
            except OSError:
                logger.exception("Can't save the job for run %s", identifier)
                raise RunsUnavailableError(CANT_SAVE) from None
            self._alive.add(identifier)
            self._waiting.put(identifier)
            self._start_worker()
            return job

    def get(self, run_id: str) -> Job | None:
        """A run's job, or None if no run with this ID was saved or submitted."""
        with self._lock:
            return self._find(run_id)

    def recover(self) -> int:
        """Mark every job left queued or running as failed, and return how many.

        Call it as the server starts, before it takes a request: whatever was running
        them stopped with the last process.
        """
        marked = 0
        for path in sorted(jobs_dir(self._settings).glob("*.json")):
            job = _read(path)
            if job is None or job.status not in ("queued", "running"):
                continue
            failed = replace(
                job, status="failed", finished_at=self._clock(), error=RESTARTED
            )
            try:
                write_job(failed, self._settings)
            except OSError:
                logger.exception("Can't mark run %s as failed", job.run_id)
                continue
            marked += 1
        if marked:
            logger.warning("Marked %d interrupted run(s) as failed", marked)
        return marked

    def close(self) -> None:
        """Take no more runs, and stop the worker once the run in progress ends. The
        worker is a daemon thread, so a stopping server doesn't wait for it."""
        with self._lock:
            self._closed = True
            self._waiting.put(None)

    def _find(self, run_id: str) -> Job | None:
        job = read_job(run_id, self._settings)
        folder = saved_run(run_id, self._settings)
        if folder is not None:
            manifest = read_document(folder, MANIFEST)
            ended = job is not None and job.status == "succeeded"
            return Job(
                run_id=run_id,
                status="succeeded",
                spec=parse_spec(manifest["spec"]),
                data_version=manifest["data_version"],
                engine_version=manifest["engine_version"],
                submitted_at=None if job is None else job.submitted_at,
                started_at=None if job is None else job.started_at,
                finished_at=job.finished_at if job is not None and ended else None,
            )
        if job is None or job.status == "succeeded":
            return None  # a job whose run's files are gone is no run at all
        if job.status == "running":
            return replace(job, progress=self._progress.get(run_id))
        return job

    def _start_worker(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(
                target=self._work, name="backtests", daemon=True
            )
            self._worker.start()

    def _work(self) -> None:
        while True:
            identifier = self._waiting.get()
            if identifier is None:
                return
            try:
                execute(
                    identifier,
                    self._settings,
                    on_decision=partial(self._note, identifier),
                    run=self._run,
                    clock=self._clock,
                )
            except Exception:
                logger.exception("Run %s couldn't be run", identifier)
            finally:
                with self._lock:
                    self._alive.discard(identifier)
                    self._progress.pop(identifier, None)

    def _note(self, run_id: str, done: int, total: int) -> None:
        with self._lock:
            self._progress[run_id] = Progress(done, total)


def _now() -> datetime:
    """The time, to the second: a job's times are for people to read."""
    return datetime.now(UTC).replace(microsecond=0)


def _written(moment: datetime | None) -> str | None:
    return None if moment is None else timestamp(moment)


def _read(path: Path) -> Job | None:
    try:
        document = json.loads(path.read_bytes())
        return Job(
            run_id=document["run_id"],
            status=document["status"],
            spec=parse_spec(document["spec"]),
            data_version=document["data_version"],
            engine_version=document["engine_version"],
            submitted_at=_time(document["submitted_at"]),
            started_at=_time(document["started_at"]),
            finished_at=_time(document["finished_at"]),
            error=document["error"],
        )
    except FileNotFoundError:
        return None
    except OSError, ValueError, KeyError, TypeError:
        logger.exception("Can't read the job in %s", path)
        return None


def _time(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)
