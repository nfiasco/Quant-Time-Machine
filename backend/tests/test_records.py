"""Run records (S7.7): the files a run saves, its run ID, and that the same inputs
always give the same bytes (app/backtest/records.py, app/runs.py).

Every test runs the canonical spec's own signals on a toy market, frozen as one data
version (`canonical_market` in tests/toy_market.py).
"""

import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from app.backtest import ENGINE_VERSION
from app.backtest.canonical import rounded
from app.backtest.metrics import summarize
from app.backtest.records import (
    MANIFEST,
    RESULT_FILES,
    RunConflictError,
    RunRecord,
    build_record,
    run_id,
    spec_hash,
    write_run,
)
from app.backtest.simulation import Simulation, simulate
from app.backtest.spec import ExperimentSpec, parse_spec
from app.config import Settings
from app.data.errors import DataVersionError
from app.data.tables import TABLES
from app.data.versions import write_manifest
from app.data.view import PointInTimeView
from app.runs import code_version, main, run_backtest, runs_dir
from tests.toy_market import INGESTED_AT, canonical_market

BACKEND = Path(__file__).resolve().parents[1]
CANONICAL = BACKEND / "tests" / "fixtures" / "specs" / "canonical.json"

DATA_VERSION = "20261019T120000Z"
"""The toy store's data version: when its rows count as ingested."""

GIT_SHA = "0123456789abcdef0123456789abcdef01234567"

TOY_PRICES = {110.0, 121.0, 133.1, 300.0}
"""Prices only the toy market's bars have. No file may hold one (D2)."""


def spec_data(**changes: Any) -> dict[str, Any]:
    """The canonical spec (roadmap §3.4) over the toy market's four months, as parsed
    JSON, with `changes` merged in."""
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    data["period"] = {"start": "2021-01-01", "end": "2021-04-30"}
    return data | changes


def spec(**changes: Any) -> ExperimentSpec:
    return parse_spec(spec_data(**changes))


@pytest.fixture
def store(store_dir: Path) -> Path:
    """The toy market, frozen as DATA_VERSION."""
    canonical_market(store_dir)
    version = write_manifest(store_dir, TABLES.values(), now=INGESTED_AT)
    assert version is not None and version.data_version == DATA_VERSION
    return store_dir


@pytest.fixture
def settings(store: Path) -> Settings:
    return Settings(_env_file=None, data_dir=store.parent, git_sha=GIT_SHA)


@pytest.fixture
def simulation(store: Path) -> Simulation:
    views = partial(PointInTimeView, data_version=DATA_VERSION, store=store)
    return simulate(spec(), views)


@pytest.fixture
def runs(tmp_path: Path) -> Path:
    """An empty folder to save runs in."""
    return tmp_path / "runs"


def files(folder: Path) -> dict[str, bytes]:
    """Every file in a run's folder, by name."""
    return {path.name: path.read_bytes() for path in sorted(folder.iterdir())}


def documents(record: RunRecord) -> dict[str, Any]:
    return {name: json.loads(content) for name, content in record.files.items()}


def floats(value: Any) -> list[float]:
    """Every float in a parsed JSON document."""
    if isinstance(value, float):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [found for item in value for found in floats(item)]
    return []


def test_a_run_saves_everything_a_reviewer_needs(
    settings: Settings, simulation: Simulation
) -> None:
    saved = run_backtest(spec(), settings)

    assert saved.folder == runs_dir(settings.data_dir) / saved.record.run_id
    assert sorted(files(saved.folder)) == sorted([MANIFEST, *RESULT_FILES])
    assert files(saved.folder) == dict(saved.record.files)
    found = documents(saved.record)

    # What it used: the spec as it ran, its hash, and the versions of data and code.
    run = found["run.json"]
    assert run["run_id"] == saved.record.run_id == run_id(spec(), DATA_VERSION)
    assert run["spec"] == spec().model_dump(mode="json")
    assert run["spec"]["portfolio"]["rank"] is None  # a default, written out
    assert run["spec_hash"] == spec_hash(spec())
    assert run["data_version"] == DATA_VERSION
    assert run["engine_version"] == ENGINE_VERSION
    assert run["git_sha"] == GIT_SHA
    assert run["record_version"] == 3

    # What it produced: returns, holdings, trades, metrics, warnings, and the audit.
    periods = found["returns.json"]["periods"]
    assert [p["decision"] for p in periods] == [
        "2021-01-04",
        "2021-02-01",
        "2021-03-01",
        "2021-04-01",
    ]
    assert periods[0] == {
        "decision": "2021-01-04",
        "decision_time": "2021-01-04T14:30:00Z",
        "fill_time": "2021-01-04T21:00:00Z",
        "fill": {"session": "2021-01-04", "price": "close"},
        "end": {"session": "2021-02-01", "price": "close"},
        "universe_size": 3,
        "holdings": 1,
        "trades": 1,
        "turnover": 1.0,
        "cost": 0.001,
        "gross_return": 0.0,
        "net_return": -0.001,
        "benchmark_return": 0.0,
        "risk_free_rate": 1.2,
        "value": 0.999,
    }
    curve = found["returns.json"]["equity_curve"]
    assert curve[0] == {
        "at": {"session": "2021-01-04", "price": "close"},
        "value": 1.0,
        "benchmark": 1.0,
    }
    assert [point["value"] for point in curve[1:]] == [p["value"] for p in periods]

    assert found["holdings.json"][2] == {
        "decision": "2021-03-01",
        "security_id": "alpha",
        "ticker": "AAA",
        "weight": 1.0,
        "signals": {"mom_12_1": 0.331, "rev_accel": 0.04},
        "period_return": 0.0,
        "exit": {"session": "2021-04-01", "price": "close"},
    }
    assert found["trades.json"] == [
        {
            "decision": "2021-01-04",
            "security_id": "alpha",
            "ticker": "AAA",
            "fill": {"session": "2021-01-04", "price": "close"},
            "weight_before": 0.0,
            "weight_after": 1.0,
            "traded": 1.0,
            "cost": 0.001,
        }
    ]
    metrics = summarize(simulation)
    assert found["metrics.json"]["periods"] == 4
    assert found["metrics.json"]["cagr"] == rounded(metrics.cagr)
    assert found["metrics.json"]["sharpe"] == rounded(metrics.sharpe)
    assert found["metrics.json"]["beta"] is None  # the benchmark never moved
    assert found["warnings.json"][0] == {
        "kind": "missing_signal",
        "decision": "2021-01-04",
        "message": "CCC was left out at the 2021-01-04 decision, because rev_accel "
        "had no value. No quarterly revenue was known then.",
        "security_id": "gamma",
        "ticker": "CCC",
        "signal": "rev_accel",
    }
    assert len(found["warnings.json"]) == 4
    # Those four are the gaps in the coverage report: CCC had no rev_accel at any of
    # the four decisions, so it was left out of each for lack of fundamentals.
    coverage = found["coverage.json"]
    assert coverage["decisions"] == 4
    assert coverage["totals"] == {
        "member_decisions": 12,
        "left_out": 4,
        "stopped_trading": 0,
        "missing": {"fundamentals": 4, "prices": 0},
        "signals": {"mom_12_1": 0, "rev_accel": 4},
        "no_fill_price": 0,
        "exits": 0,
    }
    assert [
        (row["ticker"], row["year"], row["left_out"]) for row in coverage["rows"]
    ] == [
        ("AAA", 2021, 0),
        ("BBB", 2021, 0),
        ("CCC", 2021, 4),
    ]
    assert coverage["exits"] == []

    # Every member at every decision, with its signals and what the decision made of
    # it: AAA held, BBB failing rev_accel > 0 (the first filter), and CCC left out
    # without rev_accel, for the reason its warning gives.
    members = found["members.json"]
    assert len(members) == 12  # three members at each of four decisions
    assert members[:3] == [
        {
            "decision": "2021-01-04",
            "security_id": "alpha",
            "ticker": "AAA",
            "name": "AAA Corp.",
            "cik": 1,
            "outcome": "held",
            "weight": 1.0,
            "signals": {"mom_12_1": 0.21, "rev_accel": 0.03},
            "reasons": {},
            "missing": [],
            "failed": [],
            "rank": None,
        },
        {
            "decision": "2021-01-04",
            "security_id": "beta",
            "ticker": "BBB",
            "name": "BBB Corp.",
            "cik": 2,
            "outcome": "failed_filter",
            "weight": None,
            "signals": {"mom_12_1": 0.21, "rev_accel": -0.03},
            "reasons": {},
            "missing": [],
            "failed": [0],
            "rank": None,
        },
        {
            "decision": "2021-01-04",
            "security_id": "gamma",
            "ticker": "CCC",
            "name": "CCC Corp.",
            "cik": None,
            "outcome": "missing_signal",
            "weight": None,
            "signals": {"mom_12_1": 0.21, "rev_accel": None},
            "reasons": {"rev_accel": "No quarterly revenue was known then."},
            "missing": ["rev_accel"],
            "failed": [],
            "rank": None,
        },
    ]
    # A holding is a member the run held, with the same weight and signals.
    held = [
        (m["decision"], m["security_id"], m["weight"], m["signals"])
        for m in members
        if m["outcome"] == "held"
    ]
    assert held == [
        (h["decision"], h["security_id"], h["weight"], h["signals"])
        for h in found["holdings.json"]
    ]

    # Every input at every decision, with when it became known.
    audit = found["audit.json"]
    assert [view["purpose"] for view in audit] == ["decision", "fill"] * 4 + ["end"]
    january = audit[0]
    assert (january["decision"], january["knowledge_time"]) == (
        "2021-01-04",
        "2021-01-04T14:30:00Z",
    )
    assert january["rows"] == sum(table["rows"] for table in january["tables"])
    for view in audit:
        for table in view["tables"]:
            assert table["latest_available_at"] <= view["knowledge_time"]
            assert re.fullmatch(r"[0-9a-f]{64}", table["sha256"])
    (macro,) = (t for t in january["tables"] if t["table"] == "macro_observations")
    assert macro["groups"] == [
        {
            "key": "TB3MS",
            "rows": 1,
            "latest_available_at": "2005-01-03T21:15:00Z",
            "latest_source_ref": "made up: TB3MS 2004-12-01 from 2005-01-03",
        }
    ]


def test_run_json_lists_each_files_size_and_hash(
    settings: Settings,
) -> None:
    saved = run_backtest(spec(), settings)
    listed = json.loads((saved.folder / MANIFEST).read_text(encoding="utf-8"))["files"]

    assert sorted(listed) == sorted(RESULT_FILES)
    for name, entry in listed.items():
        content = (saved.folder / name).read_bytes()
        assert entry == {
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }


def test_every_file_is_canonical_json(simulation: Simulation) -> None:
    record = build_record(simulation, git_sha=GIT_SHA)

    for name, content in record.files.items():
        text = content.decode("utf-8")
        again = json.dumps(
            json.loads(text), sort_keys=True, ensure_ascii=False, indent=2
        )
        assert text == again + "\n", name
        # Twelve significant digits: none of arithmetic's last ones.
        for number in floats(json.loads(text)):
            assert number == rounded(number), (name, number)


def test_no_file_holds_a_price(simulation: Simulation) -> None:
    # Tiingo's prices are for internal use only (D2).
    record = build_record(simulation, git_sha=GIT_SHA)

    for name, content in record.files.items():
        assert TOY_PRICES.isdisjoint(floats(json.loads(content))), name


def test_the_spec_hash_ignores_how_the_spec_was_written() -> None:
    data = spec_data()
    reordered = dict(reversed(data.items())) | {
        "signals": dict(reversed(data["signals"].items())),
        "portfolio": {"long_only": True, "weighting": "equal", "rank": None},
        "costs": {"bps_per_trade": 10.0},  # 10 in the fixture
    }
    spaced = json.dumps(data, indent=8)

    assert list(reordered) != list(data)
    assert spec_hash(parse_spec(reordered)) == spec_hash(spec())
    assert spec_hash(parse_spec(spaced)) == spec_hash(spec())
    assert spec_hash(spec(benchmark="QQQ")) != spec_hash(spec())
    assert spec_hash(spec(name="Another name")) != spec_hash(spec())
    # A list's order is part of the spec.
    assert spec_hash(spec(filters=data["filters"][::-1])) != spec_hash(spec())


def test_the_run_id_hashes_the_spec_the_data_version_and_the_engine_version() -> None:
    document = {
        "spec": spec().model_dump(mode="json"),
        "data_version": DATA_VERSION,
        "engine_version": "1.0.0",
    }
    text = json.dumps(
        document, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()

    assert run_id(spec(), DATA_VERSION, "1.0.0") == expected
    assert run_id(spec(benchmark="QQQ"), DATA_VERSION, "1.0.0") != expected
    assert run_id(spec(), "20261020T120000Z", "1.0.0") != expected
    assert run_id(spec(), DATA_VERSION, "1.0.1") != expected


def test_the_git_sha_is_recorded_but_isnt_part_of_the_run_id(
    simulation: Simulation,
) -> None:
    one = build_record(simulation, git_sha=GIT_SHA)
    other = build_record(simulation, git_sha=None)

    assert other.run_id == one.run_id
    assert {n: other.files[n] for n in RESULT_FILES} == {
        n: one.files[n] for n in RESULT_FILES
    }
    assert documents(other)["run.json"]["git_sha"] is None
    assert other.files[MANIFEST] != one.files[MANIFEST]


def test_a_run_that_read_the_whole_store_cant_be_recorded(store: Path) -> None:
    unpinned = simulate(spec(), partial(PointInTimeView, store=store))

    assert unpinned.data_version is None
    with pytest.raises(ValueError, match="pin its views to a data version"):
        build_record(unpinned, git_sha=GIT_SHA)


def test_a_run_needs_a_data_version(store_dir: Path) -> None:
    canonical_market(store_dir)  # rows, but no ingestion run froze them
    settings = Settings(_env_file=None, data_dir=store_dir.parent, git_sha=GIT_SHA)

    with pytest.raises(DataVersionError, match="has no data version yet"):
        run_backtest(spec(), settings)
    with pytest.raises(DataVersionError, match="no data version 20200101T000000Z"):
        run_backtest(spec(), settings, data_version="20200101T000000Z")
    assert not runs_dir(settings.data_dir).exists()


def test_the_same_inputs_give_byte_identical_files(
    settings: Settings, tmp_path: Path
) -> None:
    first = run_backtest(spec(), settings, out=tmp_path / "first")
    second = run_backtest(spec(), settings, out=tmp_path / "second")

    assert first.record == second.record
    assert first.folder.name == second.folder.name
    assert files(first.folder) == files(second.folder)
    assert len(files(first.folder)) == 9  # run.json and the eight results


def test_two_processes_give_byte_identical_files(
    settings: Settings, tmp_path: Path
) -> None:
    # Each process has its own hash seed, so anything that leaned on the order of a
    # set of strings would differ between them, though never within one.
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec_data()), encoding="utf-8")
    here = run_backtest(spec(), settings, out=tmp_path / "here")

    folders = []
    for seed in ("1", "2"):
        out = tmp_path / f"seed-{seed}"
        done = subprocess.run(
            [sys.executable, "-m", "app.runs", str(spec_file), "--out", str(out)],
            cwd=BACKEND,
            env=os.environ
            | {
                "DATA_DIR": str(settings.data_dir),
                "GIT_SHA": GIT_SHA,
                "PYTHONHASHSEED": seed,
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        assert f"Run {here.record.run_id}" in done.stdout
        folders.append(out / here.record.run_id)

    assert files(folders[0]) == files(folders[1]) == files(here.folder)


def test_a_pinned_runs_files_never_change(simulation: Simulation) -> None:
    # The same spec, data version, and engine version must give these bytes on every
    # machine, CI's Linux and a laptop alike. If a change to the engine, or to how
    # app/data reads the store, changes a hash here, raise ENGINE_VERSION in
    # app/backtest/__init__.py: the run ID then changes with the results, and both
    # can be pinned again. A change to the files' layout raises RECORD_VERSION instead.
    record = build_record(simulation, git_sha=GIT_SHA)
    listed = documents(record)["run.json"]["files"]

    # Engine 1.1.0 added the delisting return (S6.7). Its default changed no file
    # from 1.0.0's; only the spec hash and the run ID did, since the spec now writes
    # it out, and coverage.json is new. Record version 3 added members.json (S9.6)
    # and changed no other file, so the engine version and the run ID stayed.
    assert ENGINE_VERSION == "1.1.0"
    assert record.spec_hash == (
        "17eaeace5bfe1f9ed18177a1f19527c6d933a363431d58e5397fa37eef2752a7"
    )
    assert record.run_id == (
        "f96f97959ed75d9182385c509b9c54e44a835471a598337efe4a11cae8de792f"
    )
    assert {name: entry["sha256"] for name, entry in listed.items()} == {
        "audit.json": "f31e6e3055ebf1d81c712d6e7b93e51ff075aae7c00f63d8e3d599b73ef7511b",
        "coverage.json": "74a03012b67bb7de02967f5cfe50f55fcc93b31fef49bd24160c571bc691eb28",
        "holdings.json": "b76d777b90a01642945a6d2e5726048be79bbdab2eddd9ac29ab0312105bdca7",
        "members.json": "e92babace3ca37506836efaca399a7c67691afbb6f264760429d27f73837add0",
        "metrics.json": "e6d44562275b62df033a476c188b592812a7bc6db4fd1f6f2421d89d9465f9b7",
        "returns.json": "c84ad14cd2e91f5fa7a618ec53d60f4be9f2158d8c29a43d3b10e9b06efcaed9",
        "trades.json": "41b4611c30d24a2c00e41695c752f3f40136a184713ddd24ef6a192b2d632851",
        "warnings.json": "5cd3469008fbe09818f043faa0dd9bd3153839c903e035705e2fc3583692b257",
    }


def test_saving_a_run_again_changes_nothing(simulation: Simulation, runs: Path) -> None:
    record = build_record(simulation, git_sha=GIT_SHA)
    folder = write_run(record, runs)
    before = {path.name: path.stat().st_mtime_ns for path in folder.iterdir()}

    # Later, from another commit: the same results, so the saved run stays as it is.
    later = build_record(simulation, git_sha="f" * 40)
    assert write_run(later, runs) == folder

    assert {path.name: path.stat().st_mtime_ns for path in folder.iterdir()} == before
    assert files(folder) == dict(record.files)
    assert [path.name for path in runs.iterdir()] == [record.run_id]


def test_different_results_for_a_saved_run_are_a_conflict(
    simulation: Simulation, runs: Path
) -> None:
    record = build_record(simulation, git_sha=GIT_SHA)
    folder = write_run(record, runs)
    # The same inputs, so the same run ID, but the engine now answers differently.
    changed = dataclasses.replace(
        record, files=record.files | {"returns.json": b'{"periods": []}\n'}
    )

    with pytest.raises(RunConflictError) as error:
        write_run(changed, runs)

    assert "different results: returns.json." in str(error.value)
    assert "ENGINE_VERSION" in str(error.value)
    assert files(folder) == dict(record.files)  # the saved run is untouched

    assert write_run(changed, runs, overwrite=True) == folder
    assert files(folder) == dict(changed.files)
    assert [path.name for path in runs.iterdir()] == [record.run_id]


def test_a_run_missing_a_file_is_saved_again(
    simulation: Simulation, runs: Path
) -> None:
    record = build_record(simulation, git_sha=GIT_SHA)
    folder = write_run(record, runs)
    (folder / MANIFEST).unlink()

    assert write_run(record, runs) == folder
    assert files(folder) == dict(record.files)


def as_saved_before(folder: Path, name: str, record_version: int) -> None:
    """Make a saved run look as an older layout saved it, without one of its files."""
    (folder / name).unlink()
    manifest = json.loads((folder / MANIFEST).read_bytes())
    del manifest["files"][name]
    manifest["record_version"] = record_version
    (folder / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")


def test_a_run_saved_with_an_older_layout_gains_its_new_files(
    simulation: Simulation, runs: Path
) -> None:
    record = build_record(simulation, git_sha=GIT_SHA)
    folder = write_run(record, runs)
    as_saved_before(folder, "members.json", record_version=2)  # S9.6 added it

    # Saving the same results again adds it, without overwrite: none of them differs.
    assert write_run(record, runs) == folder

    assert files(folder) == dict(record.files)
    assert json.loads((folder / MANIFEST).read_bytes())["record_version"] == 3


def test_an_older_layout_with_different_results_is_still_a_conflict(
    simulation: Simulation, runs: Path
) -> None:
    record = build_record(simulation, git_sha=GIT_SHA)
    folder = write_run(record, runs)
    as_saved_before(folder, "members.json", record_version=2)
    changed = dataclasses.replace(
        record, files=record.files | {"returns.json": b'{"periods": []}\n'}
    )

    with pytest.raises(RunConflictError) as error:
        write_run(changed, runs)

    assert "different results: returns.json." in str(error.value)
    assert not (folder / "members.json").exists()  # the saved run is untouched


def test_the_code_version_is_the_setting_or_gits_head() -> None:
    assert code_version(Settings(_env_file=None, git_sha=GIT_SHA)) == GIT_SHA

    # Without the setting it's asked of git: a commit, "-dirty" if files have changed,
    # or nothing where there's no checkout, as in the container.
    found = code_version(Settings(_env_file=None, git_sha=None))
    assert found is None or re.fullmatch(r"[0-9a-f]{40}(-dirty)?", found)


def test_the_command_reports_the_runs_coverage(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("app.runs.get_settings", lambda: settings)
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec_data()), encoding="utf-8")

    assert main([str(spec_file), "--out", str(tmp_path / "runs")]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert (
        "  coverage      12 member-decisions, 4 left out for lack of data: 4 without "
        "fundamentals"
    ) in lines
    assert "  exits         none" in lines


def test_the_command_reports_an_invalid_spec(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(
        json.dumps(spec_data(benchmark="spy", costs={})), encoding="utf-8"
    )

    assert main([str(spec_file)]) == 2
    assert main([str(tmp_path / "missing.json")]) == 2

    errors = capsys.readouterr().err.splitlines()
    assert errors[0].startswith("benchmark must be")
    assert errors[1] == "costs.bps_per_trade is required."
    assert errors[2].startswith("Can't read the spec:")
