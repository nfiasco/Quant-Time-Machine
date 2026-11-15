"""Running a spec against the store, and saving its record (S7.7; doc/reference/runs.md).

The engine in app/backtest/ never learns where the store is: it gets a view factory.
This module is where the two meet. `run_backtest(spec, settings)`:

1. pins the run to a data version, the store's newest unless one is named;
2. runs the spec through views pinned to it (`simulate`);
3. builds the run's record, with the commit the code ran from (`code_version`);
4. saves it in DATA_DIR/runs/<run ID>/ (`write_run`).

From `backend/`, the same thing for a spec in a file:

    uv run python -m app.runs tests/fixtures/specs/canonical.json

The same spec, data version, and engine version always give the same run ID and the
same files, so running it again changes nothing.
"""

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from app.backtest.records import (
    RunConflictError,
    RunRecord,
    build_record,
    write_run,
)
from app.backtest.schedule import ScheduleError
from app.backtest.simulation import simulate
from app.backtest.spec import ExperimentSpec, SpecError, parse_spec
from app.config import BACKEND_DIR, Settings, get_settings
from app.data.errors import DataVersionError
from app.data.store import store_dir
from app.data.versions import latest_data_version
from app.data.view import PointInTimeView


@dataclass(frozen=True)
class SavedRun:
    """A run, and the folder its files are in."""

    record: RunRecord
    folder: Path


def runs_dir(data_dir: Path) -> Path:
    """Where runs are saved: DATA_DIR/runs, one folder for each run ID."""
    return data_dir / "runs"


def run_backtest(
    spec: ExperimentSpec,
    settings: Settings,
    *,
    data_version: str | None = None,
    out: Path | None = None,
    overwrite: bool = False,
) -> SavedRun:
    """Run `spec` on the store, pinned to a data version, and save its record.

    `data_version` defaults to the store's newest, and `out`, the folder that holds
    each run's own, to DATA_DIR/runs. Raises DataVersionError if the store has no data
    version yet, or not the one named; SpecError or ScheduleError for a spec the engine
    can't run; and RunConflictError if the run is already saved with different
    results, unless `overwrite` (app/backtest/records.py).
    """
    store = store_dir(settings.data_dir)
    if data_version is None:
        data_version = latest_data_version(store)
        if data_version is None:
            raise DataVersionError(
                f"The store in {store} has no data version yet, and a run must be "
                "pinned to one: ingest a source first (python -m app.data.ingest)"
            )
    views = partial(PointInTimeView, data_version=data_version, store=store)
    record = build_record(simulate(spec, views), git_sha=code_version(settings))
    folder = write_run(
        record, runs_dir(settings.data_dir) if out is None else out, overwrite=overwrite
    )
    return SavedRun(record, folder)


def code_version(settings: Settings) -> str | None:
    """The commit the code is running from, for a run's record.

    The `git_sha` setting if there is one, as on Railway. Otherwise git's HEAD, with
    "-dirty" after it when files that git tracks have changes that aren't committed,
    because the commit alone wouldn't reproduce the run. None when neither is known,
    as in a container without the setting.
    """
    if settings.git_sha:
        return settings.git_sha
    head = _git("rev-parse", "HEAD")
    if not head:
        return None
    changes = _git("status", "--porcelain", "--untracked-files=no")
    return f"{head}-dirty" if changes else head


def _git(*arguments: str) -> str | None:
    """A git command's output for this checkout, or None if it can't be run."""
    try:
        done = subprocess.run(
            ["git", *arguments],
            cwd=BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except OSError, subprocess.SubprocessError:
        return None
    return done.stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.runs",
        description="Run an experiment spec on the local store and save its record.",
    )
    parser.add_argument("spec", type=Path, help="the spec's JSON file")
    parser.add_argument(
        "--data-version",
        help="the data version to read (default: the store's newest)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="the folder to save the run's folder in (default: DATA_DIR/runs)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace a saved run whose results differ, instead of stopping",
    )
    args = parser.parse_args(argv)

    try:
        spec = parse_spec(args.spec.read_text(encoding="utf-8"))
    except OSError as error:
        print(f"Can't read the spec: {error}", file=sys.stderr)
        return 2
    except SpecError as error:
        for problem in error.problems:
            print(problem.message, file=sys.stderr)
        return 2

    started = time.monotonic()
    try:
        saved = run_backtest(
            spec,
            get_settings(),
            data_version=args.data_version,
            out=args.out,
            overwrite=args.overwrite,
        )
    except SpecError as error:
        for problem in error.problems:
            print(problem.message, file=sys.stderr)
        return 2
    except (ScheduleError, DataVersionError, RunConflictError) as error:
        print(error, file=sys.stderr)
        return 1
    print(_report(saved, time.monotonic() - started))
    return 0


def _report(saved: SavedRun, seconds: float) -> str:
    """What the command prints: the run's identity, its headline numbers, and where
    its files are."""
    record = saved.record
    files = {name: json.loads(content) for name, content in record.files.items()}
    metrics, audit = files["metrics.json"], files["audit.json"]
    start, end = metrics["start"], metrics["end"]
    rows = sum(view["rows"] for view in audit)
    facts = {
        "spec hash": record.spec_hash,
        "data version": record.data_version,
        "engine": f"{record.engine_version}, git {record.git_sha or 'unknown'}",
        "periods": (
            f"{metrics['periods']}, from the {start['session']} {start['price']} to "
            f"the {end['session']} {end['price']}"
        ),
        "CAGR": (
            f"{_percent(metrics['cagr'])}, against the benchmark's "
            f"{_percent(metrics['benchmark_cagr'])}"
        ),
        "Sharpe ratio": (
            f"{_number(metrics['sharpe'])}, with a maximum drawdown of "
            f"{_percent(metrics['max_drawdown'])}"
        ),
        "warnings": f"{len(files['warnings.json']):,}",
        "audit": f"{rows:,} rows read through {len(audit):,} views",
        "took": f"{seconds:.1f} seconds",
        "saved in": str(saved.folder),
    }
    lines = [f"  {label:<13} {fact}" for label, fact in facts.items()]
    return "\n".join([f"Run {record.run_id}", *lines])


def _percent(value: float | None) -> str:
    return "no value" if value is None else f"{value:.2%}"


def _number(value: float | None) -> str:
    return "no value" if value is None else f"{value:.2f}"


if __name__ == "__main__":
    sys.exit(main())
