"""POST /v1/backtests and GET /v1/backtests/{run_id}, with /audit, /holdings, and
/trades (S8.4; app/api/backtests.py).

Every run is the canonical spec's own signals on the toy market, frozen as one data
version (`canonical_market` in tests/toy_market.py). tests/test_run_queue.py checks
the queue behind these routes without HTTP.
"""

import dataclasses
import json
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.api import backtests
from app.api.examples import CANONICAL_SPEC
from app.backtest import (
    ENGINE_VERSION,
    audit,
    coverage,
    metrics,
    portfolio,
    returns,
    simulation,
)
from app.backtest.canonical import sha256_hex
from app.backtest.records import MANIFEST, run_id, spec_hash
from app.backtest.spec import ExperimentSpec, parse_spec
from app.config import Settings
from app.data.tables import TABLES
from app.data.versions import write_manifest
from app.main import create_app
from app.run_queue import (
    BROKE,
    BUSY,
    CANT_SAVE,
    MAX_WAITING,
    RESTARTED,
    Job,
    RunQueue,
    jobs_dir,
    write_job,
)
from app.runs import read_document, run_backtest, runs_dir
from tests.toy_market import (
    CANONICAL_SPEC as CANONICAL_FILE,
)
from tests.toy_market import (
    INGESTED_AT,
    canonical_market,
    canonical_spec_data,
)

DATA_VERSION = "20261019T120000Z"
"""The toy store's data version: when its rows count as ingested."""

GIT_SHA = "0123456789abcdef0123456789abcdef01234567"

TOY_PRICES = {110.0, 121.0, 133.1, 300.0}
"""Prices only the toy market's bars have. No response may hold one (D2)."""

RUN_ID = run_id(parse_spec(canonical_spec_data()), DATA_VERSION)
"""The canonical spec's run on the toy store."""


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
def client(settings: Settings) -> Iterator[TestClient]:
    """The API on the toy store, started and stopped as a server is."""
    with TestClient(create_app(settings)) as started:
        yield started


class Held:
    """A runner that reports one decision of four, then waits to be released, and
    then runs the spec."""

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
        run_backtest(spec, settings, data_version=options["data_version"])


@pytest.fixture
def held(client: TestClient, settings: Settings) -> Iterator[Held]:
    """The API's runs, held until a test releases them."""
    runner = Held()
    client.app.state.run_queue = RunQueue(settings, run=runner)  # type: ignore[attr-defined]
    yield runner
    runner.release.set()  # so no test leaves a thread waiting


def submit(client: TestClient, **changes: Any) -> Any:
    return client.post("/v1/backtests", json=canonical_spec_data(**changes))


def finished(client: TestClient, identifier: str = RUN_ID) -> dict[str, Any]:
    """A run's answer once it has succeeded or failed, polling as a page would."""
    for _ in range(3000):
        body = client.get(f"/v1/backtests/{identifier}").json()
        if body["status"] in ("succeeded", "failed"):
            return body
        time.sleep(0.01)
    raise AssertionError(f"run {identifier} never finished")


def saved(settings: Settings, name: str, identifier: str = RUN_ID) -> Any:
    """One of a saved run's files, as parsed JSON."""
    return read_document(runs_dir(settings.data_dir) / identifier, name)


def instant(text: str) -> datetime:
    return datetime.fromisoformat(text)


def in_new_york(text: str) -> bool:
    """Whether a timestamp is written with one of New York's offsets."""
    return text.endswith(("-05:00", "-04:00"))


def without_security_id(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entry.items() if key != "security_id"}


def floats(value: Any) -> list[float]:
    """Every float in a parsed JSON document."""
    if isinstance(value, float):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [found for item in value for found in floats(item)]
    return []


def test_submitting_a_spec_answers_with_its_run_id_at_once(
    client: TestClient, held: Held
) -> None:
    response = submit(client)

    assert response.status_code == 202
    assert response.json() == {"run_id": RUN_ID, "status": "queued"}
    assert len(RUN_ID) == 64


def test_a_submitted_run_runs_and_serves_its_result(
    client: TestClient, settings: Settings
) -> None:
    before = datetime.now(UTC).replace(microsecond=0)  # a job's times are whole seconds
    assert submit(client).status_code == 202

    run = finished(client)

    spec = parse_spec(canonical_spec_data())
    assert run["status"] == "succeeded"
    assert (run["progress"], run["error"]) == (None, None)
    assert run["run_id"] == RUN_ID
    assert run["spec"] == saved(settings, "run.json")["spec"]
    assert run["spec"]["portfolio"]["rank"] is None  # a default, written out
    assert run["spec_hash"] == spec_hash(spec)
    assert run["data_version"] == DATA_VERSION
    assert run["engine_version"] == ENGINE_VERSION
    assert run["git_sha"] == GIT_SHA
    times = [run[key] for key in ("submitted_at", "started_at", "finished_at")]
    assert all(in_new_york(text) for text in times)
    assert before <= instant(times[0]) <= instant(times[1]) <= instant(times[2])

    result = run["result"]
    assert result["metrics"] == saved(settings, "metrics.json")
    assert result["equity_curve"] == saved(settings, "returns.json")["equity_curve"]
    assert result["warnings"] == [
        without_security_id(warning) for warning in saved(settings, "warnings.json")
    ]
    assert {warning["kind"] for warning in result["warnings"]} == {"missing_signal"}


def test_a_periods_times_are_written_in_new_york_time(
    client: TestClient, settings: Settings
) -> None:
    submit(client)
    periods = finished(client)["result"]["periods"]
    files = saved(settings, "returns.json")["periods"]

    assert [period["decision"] for period in periods] == [
        "2021-01-04",
        "2021-02-01",
        "2021-03-01",
        "2021-04-01",
    ]
    # A decision at 09:30 ET, and its fill at that day's close: -05:00 in winter, and
    # -04:00 once clocks change in March. The files have the same instants in UTC.
    assert periods[0]["decision_time"] == "2021-01-04T09:30:00-05:00"
    assert periods[0]["fill_time"] == "2021-01-04T16:00:00-05:00"
    assert periods[3]["decision_time"] == "2021-04-01T09:30:00-04:00"
    assert files[0]["decision_time"] == "2021-01-04T14:30:00Z"
    for period, file in zip(periods, files, strict=True):
        for key in ("decision_time", "fill_time"):
            assert instant(period.pop(key)) == instant(file.pop(key))
        assert period == file  # and everything else as it's saved


def test_submitting_a_saved_run_again_runs_nothing(
    client: TestClient, settings: Settings
) -> None:
    submit(client)
    first = finished(client)
    held = Held()
    client.app.state.run_queue = RunQueue(settings, run=held)  # type: ignore[attr-defined]

    again = submit(client)

    assert again.status_code == 200
    assert again.json() == {"run_id": RUN_ID, "status": "succeeded"}
    assert held.ran == []
    assert finished(client) == first


def test_the_same_spec_written_another_way_is_the_same_run(
    client: TestClient, held: Held
) -> None:
    # The ID hashes the validated spec: the order of its keys, its spacing, and a
    # default that's written out don't change it.
    data = canonical_spec_data()
    data["portfolio"] = {"rank": None, **data["portfolio"]}
    reordered = json.dumps(dict(reversed(data.items())), indent=4)

    response = client.post("/v1/backtests", content=reordered)

    assert response.json()["run_id"] == RUN_ID


def test_a_run_saved_by_the_command_line_is_served(
    client: TestClient, settings: Settings
) -> None:
    run_backtest(parse_spec(canonical_spec_data()), settings)

    run = client.get(f"/v1/backtests/{RUN_ID}").json()

    assert run["status"] == "succeeded"
    assert run["result"]["metrics"] == saved(settings, "metrics.json")
    assert (run["submitted_at"], run["started_at"], run["finished_at"]) == (None,) * 3
    assert submit(client).status_code == 200


def test_a_run_in_progress_says_how_far_it_is(client: TestClient, held: Held) -> None:
    submit(client)
    assert held.started.wait(timeout=30)

    run = client.get(f"/v1/backtests/{RUN_ID}").json()

    assert run["status"] == "running"
    assert run["progress"] == {"decisions_done": 1, "decisions_total": 4}
    assert (run["result"], run["error"], run["git_sha"]) == (None, None, None)
    assert run["started_at"] is not None and run["finished_at"] is None
    assert run["spec"]["name"] == canonical_spec_data()["name"]
    assert run["data_version"] == DATA_VERSION

    again = submit(client)  # the same run, not a second one
    assert (again.status_code, again.json()["status"]) == (202, "running")
    held.release.set()
    assert finished(client)["status"] == "succeeded"
    assert held.ran == [canonical_spec_data()["name"]]


@pytest.mark.parametrize(
    ("part", "key"),
    [
        ("audit", "views"),
        ("holdings", "holdings"),
        ("trades", "trades"),
        ("coverage", "coverage"),
    ],
)
def test_a_run_in_progress_has_no_files_to_serve_yet(
    client: TestClient, held: Held, part: str, key: str
) -> None:
    submit(client)
    assert held.started.wait(timeout=30)

    response = client.get(f"/v1/backtests/{RUN_ID}/{part}")

    assert response.status_code == 200
    assert response.json() == {"run_id": RUN_ID, "status": "running", key: None}


def test_a_full_queue_answers_503(client: TestClient, held: Held) -> None:
    submit(client, name="running")
    assert held.started.wait(timeout=30)
    for number in range(MAX_WAITING):
        assert submit(client, name=f"waiting {number}").json()["status"] == "queued"

    response = submit(client, name="one too many")

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "runs_unavailable", "message": BUSY, "details": []}
    }


def test_a_server_that_cant_save_runs_answers_503(
    client: TestClient, settings: Settings
) -> None:
    # As deployed before its volume has a folder the server can write to.
    runs_dir(settings.data_dir).write_text("not a folder", encoding="utf-8")

    response = submit(client)

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "runs_unavailable",
        "message": CANT_SAVE,
        "details": [],
    }


INVALID = [
    ({"costs": None}, "costs", "costs must be an object."),
    (
        {"signals": {"mom_12_1": {"type": "momentum", "lookback_months": 0}}},
        "signals.mom_12_1.lookback_months",
        "signals.mom_12_1.lookback_months must be at least 1.",
    ),
    (
        {"leverage": 2},
        "leverage",
        "leverage isn't part of experiment spec version 1.",
    ),
    (
        {"portfolio": {"weighting": "value", "long_only": True}},
        "portfolio.weighting",
        (
            "portfolio.weighting must be 'equal' for now: value weights aren't "
            "supported yet."
        ),
    ),
    (
        {"period": {"start": "2021-01-05", "end": "2021-01-29"}},
        "period",
        (
            "period must include a decision whose trades fill before its last close, "
            "on 2021-01-29."
        ),
    ),
]
"""A change to the canonical spec, the field a 422 names for it, and its sentence: the
first three from the spec's own rules, and the last two from the engine's."""


@pytest.mark.parametrize(
    ("changes", "field", "message"),
    INVALID,
    ids=["wrong type", "signal parameter", "unknown key", "value weights", "period"],
)
def test_an_invalid_spec_answers_422_with_the_fields_path(
    client: TestClient,
    settings: Settings,
    changes: dict[str, Any],
    field: str,
    message: str,
) -> None:
    response = submit(client, **changes)

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": message,
            "details": [{"field": field, "message": message}],
        }
    }
    assert not jobs_dir(settings).exists()  # nothing was queued


def test_every_invalid_field_is_named(client: TestClient) -> None:
    data = canonical_spec_data(benchmark="spy")
    del data["costs"]

    error = client.post("/v1/backtests", json=data).json()["error"]

    assert [detail["field"] for detail in error["details"]] == ["benchmark", "costs"]
    assert error["message"] == (
        "benchmark must be a ticker in capitals, such as SPY. costs is required."
    )


@pytest.mark.parametrize("body", [b"", b"{", b"not json"])
def test_a_body_that_isnt_json_answers_422(client: TestClient, body: bytes) -> None:
    response = client.post("/v1/backtests", content=body)

    assert response.status_code == 422
    (detail,) = response.json()["error"]["details"]
    assert detail["field"] == "spec"
    assert detail["message"].startswith("The spec isn't valid JSON")


def test_a_spec_only_the_data_can_refuse_fails_with_what_is_wrong(
    client: TestClient,
) -> None:
    response = submit(client, benchmark="NOPE")
    assert response.status_code == 202

    run = finished(client, response.json()["run_id"])

    assert run["status"] == "failed"
    assert run["error"] == (
        "benchmark must be a ticker in our data, but no security used NOPE at the "
        "2021-01-04 decision."
    )
    assert run["result"] is None and run["finished_at"] is not None


def test_a_problem_of_ours_fails_a_run_without_saying_what_it_was(
    client: TestClient, settings: Settings
) -> None:
    def broken(*arguments: Any, **options: Any) -> None:
        raise RuntimeError(f"can't read {settings.data_dir}/store/price_bars")

    client.app.state.run_queue = RunQueue(settings, run=broken)  # type: ignore[attr-defined]
    submit(client)

    run = finished(client)

    assert (run["status"], run["error"]) == ("failed", BROKE)
    assert str(settings.data_dir) not in json.dumps(run)


def test_a_failed_run_can_be_submitted_again(
    client: TestClient, settings: Settings
) -> None:
    def broken(*arguments: Any, **options: Any) -> None:
        raise RuntimeError("once")

    client.app.state.run_queue = RunQueue(settings, run=broken)  # type: ignore[attr-defined]
    submit(client)
    assert finished(client)["status"] == "failed"
    client.app.state.run_queue = RunQueue(settings)  # type: ignore[attr-defined]

    assert submit(client).status_code == 202
    assert finished(client)["status"] == "succeeded"


def interrupted(settings: Settings) -> Job:
    """A job as a server that stopped mid-run leaves it."""
    job = Job(
        run_id=RUN_ID,
        status="running",
        spec=parse_spec(canonical_spec_data()),
        data_version=DATA_VERSION,
        engine_version=ENGINE_VERSION,
        submitted_at=datetime(2026, 11, 15, 17, tzinfo=UTC),
        started_at=datetime(2026, 11, 15, 17, 0, 1, tzinfo=UTC),
    )
    write_job(job, settings)
    return job


def test_a_run_interrupted_by_a_restart_is_marked_failed(settings: Settings) -> None:
    interrupted(settings)

    with TestClient(create_app(settings)) as restarted:
        run = restarted.get(f"/v1/backtests/{RUN_ID}").json()

        assert (run["status"], run["error"]) == ("failed", RESTARTED)
        assert run["submitted_at"] == "2026-11-15T12:00:00-05:00"
        assert run["finished_at"] is not None and run["result"] is None
        # And submitting it again runs it.
        assert submit(restarted).status_code == 202
        assert finished(restarted)["status"] == "succeeded"


def test_building_an_app_doesnt_fail_another_servers_run(settings: Settings) -> None:
    # A test, or anything else that imports the app, builds one without starting it.
    interrupted(settings)

    built = TestClient(create_app(settings))

    assert built.get(f"/v1/backtests/{RUN_ID}").json()["status"] == "running"


@pytest.mark.parametrize("part", ["", "/audit", "/holdings", "/trades", "/coverage"])
@pytest.mark.parametrize(
    "identifier",
    ["0" * 64, "abc", RUN_ID.upper(), "_jobs", RUN_ID + "0", "%2E%2E"],
    ids=["unknown", "short", "capitals", "jobs folder", "long", "dots"],
)
def test_an_id_that_names_no_run_answers_404(
    client: TestClient, settings: Settings, part: str, identifier: str
) -> None:
    run_backtest(parse_spec(canonical_spec_data()), settings)  # there is a run

    response = client.get(f"/v1/backtests/{identifier}{part}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_the_audit_shows_what_each_view_read(
    client: TestClient, settings: Settings
) -> None:
    submit(client)
    finished(client)

    body = client.get(f"/v1/backtests/{RUN_ID}/audit").json()

    files = saved(settings, "audit.json")
    views = body["views"]
    assert (body["run_id"], body["status"]) == (RUN_ID, "succeeded")
    assert [(view["purpose"], view["decision"], view["rows"]) for view in views] == [
        (view["purpose"], view["decision"], view["rows"]) for view in files
    ]
    # Four decisions and their fills, and the period's end.
    assert [view["purpose"] for view in views] == ["decision", "fill"] * 4 + ["end"]
    assert views[0]["knowledge_time"] == "2021-01-04T09:30:00-05:00"
    for view, file in zip(views, files, strict=True):
        assert instant(view["knowledge_time"]) == instant(file["knowledge_time"])
        for table, saved_table in zip(view["tables"], file["tables"], strict=True):
            assert in_new_york(table["latest_available_at"])
            # Nothing a view read was known after its time.
            assert instant(table["latest_available_at"]) <= instant(
                view["knowledge_time"]
            )
            assert table["sha256"] == saved_table["sha256"]
            assert [group["key"] for group in table["groups"]] == [
                group["key"] for group in saved_table["groups"]
            ]


def test_the_audit_of_one_decision(client: TestClient) -> None:
    submit(client)
    finished(client)

    views = client.get(
        f"/v1/backtests/{RUN_ID}/audit", params={"decision": "2021-02-01"}
    ).json()["views"]

    assert [(view["purpose"], view["decision"]) for view in views] == [
        ("decision", "2021-02-01"),
        ("fill", "2021-02-01"),
    ]
    facts = next(t for t in views[0]["tables"] if t["table"] == "xbrl_facts")
    assert [group["key"] for group in facts["groups"]] == [1, 2]  # CIKs


def test_holdings_and_trades_are_served_without_internal_ids(
    client: TestClient, settings: Settings
) -> None:
    submit(client)
    finished(client)

    holdings = client.get(f"/v1/backtests/{RUN_ID}/holdings").json()
    trades = client.get(f"/v1/backtests/{RUN_ID}/trades").json()

    assert (holdings["run_id"], holdings["status"]) == (RUN_ID, "succeeded")
    assert holdings["holdings"] == [
        without_security_id(holding) for holding in saved(settings, "holdings.json")
    ]
    assert trades["trades"] == [
        without_security_id(trade) for trade in saved(settings, "trades.json")
    ]
    # Alpha alone passes both filters, at each of the four decisions.
    assert [(h["decision"], h["ticker"]) for h in holdings["holdings"]] == [
        (day, "AAA") for day in ("2021-01-04", "2021-02-01", "2021-03-01", "2021-04-01")
    ]
    assert "security_id" not in json.dumps([holdings, trades])


def test_a_runs_coverage_is_served_without_internal_ids(
    client: TestClient, settings: Settings
) -> None:
    submit(client)
    finished(client)

    found = client.get(f"/v1/backtests/{RUN_ID}/coverage").json()

    report = saved(settings, "coverage.json")
    assert (found["run_id"], found["status"]) == (RUN_ID, "succeeded")
    assert found["coverage"] == report | {
        "rows": [without_security_id(row) for row in report["rows"]],
        "exits": [without_security_id(entry) for entry in report["exits"]],
    }
    # CCC had no rev_accel at any decision of the toy market's four.
    assert found["coverage"]["totals"]["left_out"] == 4
    assert found["coverage"]["totals"]["missing"] == {"fundamentals": 4, "prices": 0}
    assert "security_id" not in json.dumps(found)


def test_a_run_saved_before_engine_1_1_is_still_served(
    client: TestClient, settings: Settings
) -> None:
    # Engine 1.0.0's runs had no coverage.json, and their specs no delisting section.
    run_backtest(parse_spec(canonical_spec_data()), settings)
    folder = settings.data_dir / "runs" / RUN_ID
    (folder / "coverage.json").unlink()
    manifest = json.loads((folder / MANIFEST).read_bytes())
    del manifest["spec"]["delisting"]
    manifest |= {
        "spec_hash": sha256_hex(manifest["spec"]),
        "engine_version": "1.0.0",
        "record_version": 1,
    }
    (folder / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")

    run = client.get(f"/v1/backtests/{RUN_ID}").json()
    found = client.get(f"/v1/backtests/{RUN_ID}/coverage").json()

    # Its spec reads back with the default it ran with, and the hash it was saved with.
    assert run["status"] == "succeeded"
    assert run["spec"]["delisting"] == {"assumed_return": 0.0}
    assert (
        run["spec_hash"]
        == manifest["spec_hash"]
        != spec_hash(parse_spec(canonical_spec_data()))
    )
    assert run["engine_version"] == "1.0.0"
    assert found == {"run_id": RUN_ID, "status": "succeeded", "coverage": None}


@pytest.mark.parametrize(
    ("part", "key"), [("holdings", "holdings"), ("trades", "trades")]
)
def test_one_decisions_holdings_and_trades(
    client: TestClient, part: str, key: str
) -> None:
    submit(client)
    finished(client)
    path = f"/v1/backtests/{RUN_ID}/{part}"

    one = client.get(path, params={"decision": "2021-01-04"}).json()[key]
    none = client.get(path, params={"decision": "2021-01-05"}).json()[key]

    assert [entry["decision"] for entry in one] == ["2021-01-04"]
    assert none == []  # no decision that day


def test_a_decision_must_be_a_date(client: TestClient) -> None:
    submit(client)
    finished(client)

    response = client.get(f"/v1/backtests/{RUN_ID}/audit", params={"decision": "June"})

    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {"field": "decision", "message": "decision must be a date such as 2020-04-01."}
    ]


def test_no_response_holds_a_price(client: TestClient) -> None:
    submit(client)
    answers = [finished(client)] + [
        client.get(f"/v1/backtests/{RUN_ID}/{part}").json()
        for part in ("audit", "holdings", "trades", "coverage")
    ]

    assert not TOY_PRICES & set(floats(answers))


def test_a_page_on_another_origin_can_submit(client: TestClient) -> None:
    # A JSON POST from the browser is preflighted (CORS).
    preflight = client.options(
        "/v1/backtests",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_the_docs_example_is_the_canonical_spec() -> None:
    assert CANONICAL_SPEC == json.loads(CANONICAL_FILE.read_text(encoding="utf-8"))
    parse_spec(CANONICAL_SPEC)


def test_the_docs_describe_the_body_as_an_experiment_spec(client: TestClient) -> None:
    operation = client.app.openapi()["paths"]["/v1/backtests"]["post"]  # type: ignore[attr-defined]

    body = operation["requestBody"]["content"]["application/json"]
    assert body["schema"] == {"$ref": "#/components/schemas/ExperimentSpec"}
    assert body["example"] == CANONICAL_SPEC
    assert set(operation["responses"]) == {"200", "202", "422", "500", "503"}


@pytest.mark.parametrize(
    ("model", "record", "added"),
    [
        (backtests.BacktestMetrics, metrics.Metrics, set()),
        (backtests.EquityPoint, metrics.EquityPoint, set()),
        (backtests.PricePoint, returns.PricePoint, set()),
        (backtests.BacktestWarning, simulation.SimulationWarning, set()),
        # A holding and a trade carry their decision's day, and a trade its size.
        (backtests.BacktestHolding, simulation.Holding, {"decision"}),
        (backtests.BacktestTrade, portfolio.Trade, {"decision", "traded"}),
        (backtests.AuditView, audit.ViewInputs, {"rows"}),
        (backtests.AuditTable, audit.TableInputs, set()),
        (backtests.AuditGroup, audit.InputGroup, set()),
        (backtests.CoverageReport, coverage.RunCoverage, set()),
        (backtests.CoverageCounts, coverage.CoverageCounts, set()),
        (backtests.CoverageRow, coverage.CoverageRow, set()),
        (backtests.CoverageExit, coverage.CoverageExit, set()),
    ],
)
def test_response_models_carry_every_engine_field_but_internal_ids(
    model: type[BaseModel], record: type, added: set[str]
) -> None:
    fields = {field.name for field in dataclasses.fields(record)}

    assert set(model.model_fields) == fields - {"security_id"} | added
