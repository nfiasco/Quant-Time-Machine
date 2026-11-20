"""Run records: the files that say exactly what a run used and produced (S7.7;
doc/reference/runs.md).

`build_record(simulation, git_sha=...)` turns a finished run (app/backtest/simulation.py)
into its files, and `write_run(record, runs_dir)` saves them in a folder named by the
run's ID:

- `run.json`: the run ID, the spec exactly as it ran, its hash, the data version, the
  engine version, the git SHA, and each other file's size and SHA-256.
- `returns.json`: each holding period's returns, costs, and value, and the equity
  curve beside the benchmark's.
- `holdings.json`, `trades.json`, and `warnings.json`: one entry each, with its
  decision's day.
- `metrics.json`: the run's metrics (app/backtest/metrics.py).
- `coverage.json`: what data its decisions lacked, by security and year, and its exits
  at a last close (app/backtest/coverage.py, S6.7).
- `audit.json`: what each view the run opened read (app/backtest/audit.py).

The same spec, data version, and engine version always give the same bytes:

- **The run ID** is the SHA-256 of those three (`run_id`), so it names the inputs, not
  the moment. The git SHA is recorded but isn't part of it.
- **The files are canonical JSON** (app/backtest/canonical.py), indented so two runs
  can be compared line by line, and every computed number is rounded to 12 significant
  digits. The spec isn't rounded: it's saved as it ran.
- **No file has a clock in it**: no creation time, and no duration.
- **A run that read the whole store can't be recorded.** Its views must be pinned to a
  data version, or nobody could read the same data again.

As everywhere in the engine, the files hold weights, returns, and dates, never
prices (D2).
"""

import dataclasses
import hashlib
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.backtest import ENGINE_VERSION, coverage
from app.backtest.audit import timestamp
from app.backtest.canonical import canonical_json, rounded, sha256_hex
from app.backtest.metrics import equity_curve, summarize
from app.backtest.returns import PricePoint
from app.backtest.simulation import HoldingPeriod, Simulation
from app.backtest.spec import ExperimentSpec
from app.data.timeutil import ET

RECORD_VERSION = 2
"""The version of the files' layout, in `run.json`. It isn't part of the run ID: a new
layout says the same things about the same run. Version 2 added `coverage.json`
(S6.7)."""

MANIFEST = "run.json"

RESULT_FILES = (
    "returns.json",
    "holdings.json",
    "trades.json",
    "metrics.json",
    "warnings.json",
    "coverage.json",
    "audit.json",
)
"""What a run produced. `run.json` lists each one's size and hash."""


class RunConflictError(Exception):
    """A run's folder already holds different results for the same run ID."""


@dataclass(frozen=True)
class RunRecord:
    """A run as it's saved."""

    run_id: str
    spec_hash: str
    data_version: str
    engine_version: str
    git_sha: str | None
    files: Mapping[str, bytes]
    """Each file's bytes, by name: `run.json`, then RESULT_FILES."""


def spec_hash(spec: ExperimentSpec) -> str:
    """The SHA-256 of a spec's canonical JSON.

    It hashes the validated spec, not the text it came from, so the order of its keys,
    its spacing, and whether a default was written out don't change it. The order of a
    list, such as the filters, does.
    """
    return sha256_hex(_spec(spec))


def run_id(
    spec: ExperimentSpec, data_version: str, engine_version: str = ENGINE_VERSION
) -> str:
    """A run's ID: the SHA-256 of its spec, data version, and engine version, as
    canonical JSON. The same three always give the same ID."""
    return sha256_hex(
        {
            "spec": _spec(spec),
            "data_version": data_version,
            "engine_version": engine_version,
        }
    )


def build_record(
    simulation: Simulation,
    *,
    git_sha: str | None,
    engine_version: str = ENGINE_VERSION,
) -> RunRecord:
    """A finished run's files.

    `git_sha` is the commit the engine ran from, or None if it isn't known. Raises
    ValueError for a run whose views read the whole store instead of a data version.
    """
    data_version = simulation.data_version
    if data_version is None:
        raise ValueError(
            "a run that read the whole store can't be recorded: pin its views to a "
            "data version, so the same data can be read again"
        )
    documents: dict[str, Any] = {
        "returns.json": rounded(
            {
                "periods": [_period(period) for period in simulation.periods],
                "equity_curve": _plain(equity_curve(simulation)),
            }
        ),
        "holdings.json": rounded(
            [
                {"decision": _day(period), **_plain(holding)}
                for period in simulation.periods
                for holding in period.holdings
            ]
        ),
        "trades.json": rounded(
            [
                {"decision": _day(period), **_plain(trade), "traded": trade.traded}
                for period in simulation.periods
                for trade in period.trades
            ]
        ),
        "metrics.json": rounded(_plain(summarize(simulation))),
        "warnings.json": _plain(simulation.warnings),
        "coverage.json": _plain(coverage.summarize(simulation)),
        "audit.json": [
            {**_plain(view), "rows": view.rows} for view in simulation.audit
        ],
    }
    files = {name: _file(documents[name]) for name in RESULT_FILES}
    identifier = run_id(simulation.spec, data_version, engine_version)
    hashed = spec_hash(simulation.spec)
    manifest = {
        "record_version": RECORD_VERSION,
        "run_id": identifier,
        "spec": _spec(simulation.spec),
        "spec_hash": hashed,
        "data_version": data_version,
        "engine_version": engine_version,
        "git_sha": git_sha,
        "files": {
            name: {"bytes": len(content), "sha256": _sha256(content)}
            for name, content in files.items()
        },
    }
    return RunRecord(
        run_id=identifier,
        spec_hash=hashed,
        data_version=data_version,
        engine_version=engine_version,
        git_sha=git_sha,
        files={MANIFEST: _file(manifest), **files},
    )


def write_run(record: RunRecord, runs_dir: Path, *, overwrite: bool = False) -> Path:
    """Save a run's files in `runs_dir`/<run ID>, and return that folder.

    The folder appears whole or not at all: the files are written beside it, then
    moved into place. A run that's already saved with the same results is left as it
    is, with the git SHA that first wrote it. If the results differ, the same inputs
    gave two answers, which means the engine changed without a new ENGINE_VERSION:
    that raises RunConflictError, unless `overwrite` says to replace the saved run.
    """
    folder = runs_dir / record.run_id
    if folder.exists():
        changed = [
            name for name in RESULT_FILES if _read(folder / name) != record.files[name]
        ]
        if not changed and (folder / MANIFEST).is_file():
            return folder
        if changed and not overwrite:
            raise RunConflictError(
                f"Run {record.run_id} is already saved in {folder} with different "
                f"results: {', '.join(changed)}. The same spec, data version, and "
                f"engine version ({record.engine_version}) must give the same "
                "results, so the engine changed without a new ENGINE_VERSION "
                "(app/backtest/__init__.py). Raise it, or replace the saved run "
                "with overwrite."
            )

    # Written beside the folder, then moved, so nobody reads half a run.
    partial = runs_dir / f".{record.run_id}.tmp"
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    try:
        for name, content in record.files.items():
            (partial / name).write_bytes(content)
        if folder.exists():
            shutil.rmtree(folder)
        partial.replace(folder)
    finally:
        shutil.rmtree(partial, ignore_errors=True)
    return folder


def _spec(spec: ExperimentSpec) -> dict[str, Any]:
    """A spec as JSON's types, with every default written out: `"rank": null` for a
    portfolio without a ranking."""
    return spec.model_dump(mode="json")


def _period(period: HoldingPeriod) -> dict[str, Any]:
    """A holding period's row in returns.json."""
    rebalance = period.rebalance
    return {
        "decision": _day(period),
        "decision_time": timestamp(rebalance.decision_time),
        "fill_time": timestamp(rebalance.fill_time),
        "fill": _plain(PricePoint(rebalance.fill_session, rebalance.fill_price)),
        "end": _plain(period.end),
        "universe_size": period.universe_size,
        "holdings": len(period.holdings),
        "trades": len(period.trades),
        "turnover": period.turnover,
        "cost": period.cost,
        "gross_return": period.gross_return,
        "net_return": period.net_return,
        "benchmark_return": period.benchmark_return,
        "risk_free_rate": period.risk_free_rate,
        "value": period.value,
    }


def _day(period: HoldingPeriod) -> str:
    """The New York day of a period's decision, as the warnings give it."""
    return period.rebalance.decision_time.astimezone(ET).date().isoformat()


def _plain(value: Any) -> Any:
    """The engine's records as JSON's types: a dataclass as an object of its fields,
    a time in UTC, and a date as 2020-06-01."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, datetime):
        return timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _file(document: Any) -> bytes:
    """A document as a file's bytes: canonical JSON, indented, with a last newline."""
    return (canonical_json(document, indent=2) + "\n").encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None
