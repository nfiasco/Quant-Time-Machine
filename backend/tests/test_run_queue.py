"""Background runs (S8.4): a job's file, running one, the queue, and what a restart
leaves (app/run_queue.py).

Every test runs the canonical spec's own signals on the toy market, frozen as one data
version (`canonical_market` in tests/toy_market.py). tests/test_api_backtests.py
checks the same queue through the API.
"""

import logging
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.backtest import ENGINE_VERSION
from app.backtest.records import run_id
from app.backtest.spec import ExperimentSpec, parse_spec
from app.config import Settings
from app.data.errors import DataVersionError
from app.data.tables import TABLES
from app.data.versions import write_manifest
from app.run_queue import (
    BROKE,
    BUSY,
    CANT_SAVE,
    MAX_WAITING,
    RESTARTED,
    Job,
    Progress,
    RunQueue,
    RunsUnavailableError,
    execute,
    jobs_dir,
    read_job,
    write_job,
)
from app.runs import run_backtest, runs_dir, saved_run
from tests.toy_market import INGESTED_AT, canonical_market, canonical_spec_data

DATA_VERSION = "20261019T120000Z"
"""The toy store's data version: when its rows count as ingested."""

NOON = datetime(2026, 11, 15, 17, tzinfo=UTC)


def spec(**changes: Any) -> ExperimentSpec:
    return parse_spec(canonical_spec_data(**changes))


def job(status: str = "queued", **changes: Any) -> Job:
    """A job for the canonical spec on the toy store, submitted at NOON."""
    found = spec(**changes)
    return Job(
        run_id=run_id(found, DATA_VERSION),
        status=status,  # type: ignore[arg-type]
        spec=found,
        data_version=DATA_VERSION,
        engine_version=ENGINE_VERSION,
        submitted_at=NOON,
    )


def ticking() -> Callable[[], datetime]:
    """A clock that reads a minute later each time, from a minute after NOON."""
    times = iter(NOON + timedelta(minutes=minute) for minute in range(1, 100))
    return lambda: next(times)


@pytest.fixture
def store(store_dir: Path) -> Path:
    """The toy market, frozen as DATA_VERSION."""
    canonical_market(store_dir)
    version = write_manifest(store_dir, TABLES.values(), now=INGESTED_AT)
    assert version is not None and version.data_version == DATA_VERSION
    return store_dir


@pytest.fixture
def settings(store: Path) -> Settings:
    return Settings(_env_file=None, data_dir=store.parent)


class Held:
    """A runner that reports one decision of four, then waits to be released. It
    saves nothing."""

    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.ran: list[str] = []

    def __call__(
        self, spec: ExperimentSpec, settings: Settings, **options: Any
    ) -> None:
        self.ran.append(spec.name)
        options["on_decision"](1, 4)
        self.started.set()
        assert self.release.wait(timeout=30)


@pytest.fixture
def held() -> Iterator[Held]:
    runner = Held()
    yield runner
    runner.release.set()  # so no test leaves a thread waiting


def wait_for(queue: RunQueue, identifier: str, status: str) -> Job:
    """The job once it reaches `status`, which must take under 30 seconds."""
    done = threading.Event()
    for _ in range(3000):
        found = queue.get(identifier)
        if found is not None and found.status == status:
            return found
        done.wait(0.01)
    raise AssertionError(f"run {identifier} never reached {status}")


def test_a_job_is_read_back_as_it_was_written(settings: Settings) -> None:
    written = Job(
        run_id=job().run_id,
        status="failed",
        spec=spec(),
        data_version=DATA_VERSION,
        engine_version=ENGINE_VERSION,
        submitted_at=NOON,
        started_at=NOON + timedelta(seconds=1),
        finished_at=NOON + timedelta(seconds=2),
        error="benchmark must be a ticker in our data.",
    )

    write_job(written, settings)

    assert read_job(written.run_id, settings) == written
    assert [path.name for path in jobs_dir(settings).iterdir()] == [
        f"{written.run_id}.json"  # and nothing left beside it
    ]


def test_a_job_is_kept_beside_the_runs_not_among_them(settings: Settings) -> None:
    write_job(job(), settings)

    assert jobs_dir(settings) == runs_dir(settings.data_dir) / "_jobs"
    assert saved_run("_jobs", settings) is None


def test_there_is_no_job_without_a_file_or_with_a_broken_one(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    assert read_job("0" * 64, settings) is None

    jobs_dir(settings).mkdir(parents=True)
    (jobs_dir(settings) / f"{'1' * 64}.json").write_text("{", encoding="utf-8")

    assert read_job("1" * 64, settings) is None
    assert "Can't read the job" in caplog.text


def test_executing_a_job_runs_it_and_saves_its_record(settings: Settings) -> None:
    queued = job()
    write_job(queued, settings)
    seen = []

    ended = execute(
        queued.run_id,
        settings,
        on_decision=lambda done, total: seen.append((done, total)),
        clock=ticking(),
    )

    assert ended.status == "succeeded" and ended.error is None
    assert ended.started_at == NOON + timedelta(minutes=1)
    assert ended.finished_at == NOON + timedelta(minutes=2)
    assert ended.submitted_at == NOON
    assert read_job(queued.run_id, settings) == ended
    assert saved_run(queued.run_id, settings) is not None
    assert seen == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_a_job_is_running_while_its_spec_runs(settings: Settings) -> None:
    queued = job()
    write_job(queued, settings)
    during = []

    def watched(*arguments: Any, **options: Any) -> None:
        during.append(read_job(queued.run_id, settings))

    execute(queued.run_id, settings, run=watched, clock=ticking())

    (seen,) = during
    assert seen is not None and seen.status == "running"
    assert seen.started_at == NOON + timedelta(minutes=1)
    assert seen.finished_at is None


def test_a_spec_the_engine_refuses_fails_with_what_is_wrong(
    settings: Settings,
) -> None:
    queued = job(benchmark="NOPE")
    write_job(queued, settings)

    ended = execute(queued.run_id, settings, clock=ticking())

    assert ended.status == "failed"
    assert ended.error == (
        "benchmark must be a ticker in our data, but no security used NOPE at the "
        "2021-01-04 decision."
    )
    assert ended.finished_at == NOON + timedelta(minutes=2)
    assert saved_run(queued.run_id, settings) is None


def test_a_problem_of_ours_fails_without_saying_what_it_was(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    queued = job()
    write_job(queued, settings)

    def broken(*arguments: Any, **options: Any) -> None:
        raise RuntimeError("can't read /data/store/price_bars")

    with caplog.at_level(logging.ERROR):
        ended = execute(queued.run_id, settings, run=broken)

    assert (ended.status, ended.error) == ("failed", BROKE)
    assert "price_bars" in caplog.text  # the log has it, and the job doesn't


def test_executing_needs_a_job(settings: Settings) -> None:
    with pytest.raises(LookupError):
        execute("0" * 64, settings)


def test_a_submitted_run_runs_in_the_background(settings: Settings) -> None:
    queue = RunQueue(settings, clock=ticking())

    submitted = queue.submit(spec())

    assert submitted.status == "queued"
    assert submitted.run_id == run_id(spec(), DATA_VERSION)
    assert submitted.submitted_at == NOON + timedelta(minutes=1)
    ended = wait_for(queue, submitted.run_id, "succeeded")
    assert ended.progress is None
    assert ended.spec == spec() and ended.data_version == DATA_VERSION
    assert saved_run(submitted.run_id, settings) is not None


def test_a_running_job_says_how_far_it_is(settings: Settings, held: Held) -> None:
    queue = RunQueue(settings, run=held)

    submitted = queue.submit(spec())
    assert held.started.wait(timeout=30)

    running = queue.get(submitted.run_id)
    assert running is not None and running.status == "running"
    assert running.progress == Progress(decisions_done=1, decisions_total=4)


def test_a_run_in_progress_isnt_queued_twice(settings: Settings, held: Held) -> None:
    queue = RunQueue(settings, run=held)
    first = queue.submit(spec())
    assert held.started.wait(timeout=30)

    again = queue.submit(spec())

    assert (again.run_id, again.status) == (first.run_id, "running")
    held.release.set()
    wait_for_idle(queue)
    assert held.ran == [spec().name]


def test_a_saved_run_isnt_run_again(settings: Settings, held: Held) -> None:
    saved = run_backtest(spec(), settings)  # as the command line saves one
    queue = RunQueue(settings, run=held)

    found = queue.submit(spec())

    assert (found.run_id, found.status) == (saved.record.run_id, "succeeded")
    assert found.submitted_at is None  # nobody submitted it
    assert held.ran == []
    assert read_job(found.run_id, settings) is None


def test_a_failed_run_can_be_submitted_again(settings: Settings) -> None:
    failed = job("failed")
    write_job(failed, settings)
    queue = RunQueue(settings)

    assert queue.submit(spec()).status == "queued"
    wait_for(queue, failed.run_id, "succeeded")


def test_runs_wait_their_turn_and_a_full_queue_takes_no_more(
    settings: Settings, held: Held
) -> None:
    queue = RunQueue(settings, run=held)
    queue.submit(spec(name="running"))
    assert held.started.wait(timeout=30)
    waiting = [queue.submit(spec(name=f"waiting {n}")) for n in range(MAX_WAITING)]

    assert {found.status for found in waiting} == {"queued"}
    with pytest.raises(RunsUnavailableError) as refused:
        queue.submit(spec(name="one too many"))
    assert str(refused.value) == BUSY
    assert queue.submit(spec(name="waiting 0")).status == "queued"  # it's known

    held.release.set()
    wait_for_idle(queue)
    assert held.ran == ["running", *(f"waiting {n}" for n in range(MAX_WAITING))]


def test_a_folder_that_cant_be_written_takes_no_runs(settings: Settings) -> None:
    runs_dir(settings.data_dir).write_text("not a folder", encoding="utf-8")

    with pytest.raises(RunsUnavailableError) as refused:
        RunQueue(settings).submit(spec())

    assert str(refused.value) == CANT_SAVE


def test_a_closed_queue_takes_no_runs(settings: Settings) -> None:
    queue = RunQueue(settings)
    queue.close()

    with pytest.raises(RunsUnavailableError):
        queue.submit(spec())


def test_a_store_without_a_data_version_takes_no_runs(store_dir: Path) -> None:
    canonical_market(store_dir)  # rows, but no manifest

    with pytest.raises(DataVersionError):
        RunQueue(Settings(_env_file=None, data_dir=store_dir.parent)).submit(spec())


def test_a_restart_fails_what_was_queued_or_running(settings: Settings) -> None:
    names = {"queued": "a", "running": "b", "failed": "c"}
    jobs = {status: job(status, name=name) for status, name in names.items()}
    for written in jobs.values():
        write_job(written, settings)
    queue = RunQueue(settings, clock=ticking())

    assert queue.recover() == 2

    for status in ("queued", "running"):
        found = queue.get(jobs[status].run_id)
        assert found is not None
        assert (found.status, found.error) == ("failed", RESTARTED)
        assert found.finished_at is not None
    assert queue.get(jobs["failed"].run_id) == jobs["failed"]  # as it was
    assert queue.recover() == 0


def test_a_restart_with_no_jobs_marks_nothing(settings: Settings) -> None:
    assert RunQueue(settings).recover() == 0


def test_a_saved_run_has_succeeded_whatever_its_job_says(settings: Settings) -> None:
    # The server stopped after the run's files were moved into place, and before its
    # job was updated.
    saved = run_backtest(spec(), settings)
    write_job(job("running"), settings)
    queue = RunQueue(settings)
    queue.recover()

    found = queue.get(saved.record.run_id)

    assert found is not None and found.status == "succeeded"
    assert found.error is None and found.submitted_at == NOON


def test_a_job_whose_runs_files_are_gone_is_no_run(settings: Settings) -> None:
    write_job(job("succeeded"), settings)

    assert RunQueue(settings).get(job().run_id) is None


def wait_for_idle(queue: RunQueue) -> None:
    """Wait until the queue has nothing queued or running."""
    done = threading.Event()
    for _ in range(3000):
        if not queue._alive:
            return
        done.wait(0.01)
    raise AssertionError("the queue never emptied")
