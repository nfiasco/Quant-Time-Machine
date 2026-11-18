"""POST /v1/backtests, and GET /v1/backtests/{run_id} with its /audit, /holdings,
/trades, and /coverage: submit an experiment spec, and read the run it names (S8.4,
S6.7).

- **Submitting** validates the spec the way `parse_spec` does, so a 422 names each
  field as the spec's own errors do ("signals.mom_12_1.lookback_months"), and adds
  what the engine can say before it reads any data (`check_runnable`). The answer is
  the run's ID, at once: the run itself goes in the background (app/run_queue.py),
  and the page polls `GET /v1/backtests/{run_id}` for its status.
- **A run's ID names its inputs:** the spec, the store's newest data version, and the
  engine version (app/backtest/records.py). So submitting a spec that already ran on
  the same data answers 200 with the saved run, and runs nothing.
- **Reading** serves a saved run's files (doc/reference/runs.md) as they are, with
  two changes every /v1 response makes: times are written in New York time (D12), and
  internal security IDs are left out of holdings, trades, warnings, and coverage. As in
  the files, there are weights, returns, and dates, and never a price (D2).
- **A run saved before engine 1.1.0** (record version 1) has no coverage report, so
  its `coverage` is null. Its spec reads back with the `delisting` section it didn't
  have, at the default it ran with, so its `spec_hash` comes from its run.json.

These responses have no `knowledge_time`: a run isn't an answer as of one moment. Its
`data_version` is the one the run is pinned to, not the newest now.
"""

import re
from collections.abc import Iterable
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from app.api import examples
from app.api.conventions import AppSettings, NewYorkTime
from app.api.errors import ApiError, ErrorResponse
from app.backtest.audit import Purpose
from app.backtest.coverage import ExitKind
from app.backtest.records import MANIFEST, spec_hash
from app.backtest.schedule import ScheduleError
from app.backtest.signals import DataKind
from app.backtest.simulation import WarningKind, check_runnable
from app.backtest.spec import ExperimentSpec, SpecError, SpecProblem, parse_spec
from app.config import Settings
from app.run_queue import (
    Job,
    RunQueue,
    RunStatus,
    RunsUnavailableError,
    schedule_problem,
)
from app.runs import read_document, saved_run

router = APIRouter(prefix="/backtests", tags=["backtests"])

RUN_ID = re.compile(r"[0-9a-f]{64}", re.ASCII)
"""A run ID: all 64 hex digits of a SHA-256. Checked before an ID is used as a
folder's name."""


class _Model(BaseModel):
    # Marks fields that can be null as required in the response schema, since every
    # response includes them (S8.6 generates TypeScript types from it).
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class PricePoint(_Model):
    """One session's open or close: where a trade fills or a holding is valued. It
    says which price, never what the price was (D2)."""

    session: date
    price: Literal["open", "close"]


class BacktestSubmitted(_Model):
    """A run that was submitted."""

    run_id: str = Field(
        description=(
            "The run's ID: the SHA-256 of its spec, data version, and engine version. "
            "Read the run at /v1/backtests/{run_id}."
        )
    )
    status: RunStatus = Field(
        description=(
            '"queued" or "running" for a run in progress, and "succeeded" for one '
            "that was already saved."
        )
    )


class BacktestProgress(_Model):
    """How far a running run has come."""

    decisions_done: int
    decisions_total: int


class BacktestMetrics(_Model):
    """A run's performance, after costs (doc/reference/metrics.md). Returns and rates
    are fractions: 0.05 is 5%. A metric is null when the run can't give it one."""

    periods: int = Field(description="How many holding periods the run had.")
    start: PricePoint = Field(description="The first fill, where the value is 1.")
    end: PricePoint = Field(description="The last period's end.")
    years: float
    total_return: float
    cagr: float | None
    volatility: float | None
    sharpe: float | None
    max_drawdown: float = Field(
        description="The deepest fall from an earlier peak: -0.25 fell by a quarter."
    )
    turnover: float | None = Field(
        description="The mean turnover of a rebalance after the first fill."
    )
    hit_rate: float | None = Field(
        description="The share of periods whose net return beat the benchmark's."
    )
    benchmark_total_return: float | None
    benchmark_cagr: float | None
    excess_return: float | None = Field(description="cagr less benchmark_cagr.")
    beta: float | None
    alpha: float | None
    mean_excess_return: float | None
    excess_t_stat: float | None


class BacktestPeriod(_Model):
    """A decision and the portfolio it held until the next fill."""

    decision: date = Field(description="The New York day of the decision.")
    decision_time: NewYorkTime
    fill_time: NewYorkTime = Field(description="When its trades filled.")
    fill: PricePoint
    end: PricePoint = Field(
        description="Where the period ends: the next fill, or the run's last close."
    )
    universe_size: int
    holdings: int
    trades: int
    turnover: float
    cost: float = Field(
        description="What the trades cost, a fraction of the value before trading."
    )
    gross_return: float
    net_return: float = Field(description="The period's return after costs.")
    benchmark_return: float | None
    risk_free_rate: float | None = Field(
        description=(
            "The 3-month Treasury bill rate the decision knew, in percent a year: "
            "0.09 is 0.09%."
        )
    )
    value: float = Field(
        description="The portfolio's value at the period's end. It starts at 1."
    )


class EquityPoint(_Model):
    """The portfolio's value beside the benchmark's, at the first fill and at each
    period's end."""

    at: PricePoint
    value: float
    benchmark: float | None = Field(
        description=(
            "What 1 in the benchmark at the first fill would be worth. Null from the "
            "first period without a benchmark return on."
        )
    )


class BacktestWarning(_Model):
    """Data the run did without, and what it assumed instead."""

    kind: WarningKind
    decision: date = Field(description="The New York day of the decision it concerns.")
    message: str = Field(description="A sentence the page can show as is.")
    ticker: str | None
    signal: str | None = Field(
        description='The signal\'s ID in the spec, for "missing_signal".'
    )


class BacktestResult(_Model):
    """What a run produced, apart from its holdings, trades, and audit, which have
    their own endpoints."""

    metrics: BacktestMetrics
    periods: list[BacktestPeriod]
    equity_curve: list[EquityPoint]
    warnings: list[BacktestWarning]


class BacktestRun(_Model):
    """A run: what it ran on, how far it has come, and its result once it has one."""

    run_id: str
    status: RunStatus
    progress: BacktestProgress | None = Field(
        description="How far a running run has come. Null otherwise."
    )
    submitted_at: NewYorkTime | None = Field(
        description=(
            "When it was submitted. Null for a run saved by the command line, which "
            "nobody submitted."
        )
    )
    started_at: NewYorkTime | None
    finished_at: NewYorkTime | None
    error: str | None = Field(
        description="Why a failed run failed, as a sentence the page can show as is."
    )
    spec: ExperimentSpec = Field(
        description="The spec exactly as it runs, with every default written out."
    )
    spec_hash: str
    data_version: str = Field(description="The data version the run is pinned to.")
    engine_version: str
    git_sha: str | None = Field(
        description=(
            "The commit the code that ran it came from. Null until the run is saved, "
            "and where it wasn't known."
        )
    )
    result: BacktestResult | None = Field(
        description="Null until the run has succeeded."
    )


class AuditGroup(_Model):
    """One table's rows that share their first key column."""

    key: str | int | float | bool | None = Field(
        description=(
            "That column's value: a CIK in xbrl_facts, a series ID in "
            "macro_observations, a universe's name in universe_members, and our own "
            "ID for a security in price_bars, corporate_actions, and securities."
        )
    )
    rows: int
    latest_available_at: NewYorkTime
    latest_source_ref: str


class AuditTable(_Model):
    """The rows a view returned from one table."""

    table: str
    rows: int = Field(description="How many distinct rows.")
    earliest_available_at: NewYorkTime
    latest_available_at: NewYorkTime = Field(
        description=(
            "When the newest of them became known: never after the view's "
            "knowledge_time."
        )
    )
    sha256: str = Field(
        description="A hash of every row (doc/reference/runs.md says how to check it)."
    )
    groups: list[AuditGroup]


class AuditView(_Model):
    """Everything one of the run's views read."""

    purpose: Purpose = Field(
        description=(
            '"decision" for what a decision could use, "fill" for the bars that value '
            'a period and fill its trades, and "end" for the run\'s last close.'
        )
    )
    decision: date = Field(description="The New York day of the decision it served.")
    knowledge_time: NewYorkTime = Field(description="The time the view was bound to.")
    rows: int
    tables: list[AuditTable]


class BacktestAudit(_Model):
    run_id: str
    status: RunStatus
    views: list[AuditView] | None = Field(
        description=(
            "What each view the run opened read, in the order they were opened. "
            "Null until the run has succeeded."
        )
    )


class BacktestHolding(_Model):
    """A security held from one fill to the next."""

    decision: date = Field(description="The New York day of the decision.")
    ticker: str = Field(description="Its ticker at the decision that chose it.")
    weight: float = Field(
        description="Its weight after the fill. Negative for a short."
    )
    signals: dict[str, float] = Field(
        description="Its signals' values at the decision, by their IDs in the spec."
    )
    period_return: float
    exit: PricePoint = Field(
        description=(
            "Where it was valued: the period's end, or its last close if its bars "
            "ended first."
        )
    )


class BacktestHoldings(_Model):
    run_id: str
    status: RunStatus
    holdings: list[BacktestHolding] | None = Field(
        description="In decision order. Null until the run has succeeded."
    )


class BacktestTrade(_Model):
    """One security's trade at a fill."""

    decision: date = Field(description="The New York day of the decision.")
    ticker: str | None
    fill: PricePoint
    weight_before: float
    weight_after: float = Field(description="0 for a position that's closed.")
    traded: float = Field(
        description="The value traded, a fraction of the value before trading."
    )
    cost: float


class BacktestTrades(_Model):
    run_id: str
    status: RunStatus
    trades: list[BacktestTrade] | None = Field(
        description="In decision order. Null until the run has succeeded."
    )


class CoverageCounts(_Model):
    """Member-decisions, a member of the universe at a decision each, and the gaps in
    their data."""

    member_decisions: int
    left_out: int = Field(
        description=(
            "Member-decisions left out for lack of data: the member had stopped "
            "trading, or a signal a filter or the ranking needs had no value. A "
            "member without two signals counts once."
        )
    )
    stopped_trading: int
    missing: dict[DataKind, int] = Field(
        description=(
            "Member-decisions left out because a signal reading this data had no "
            'value: "prices", "fundamentals", or "macro", for each kind the needed '
            "signals read. A member without two kinds counts once in each."
        )
    )
    signals: dict[str, int] = Field(
        description=(
            "Member-decisions at which each needed signal had no value, by its ID in "
            "the spec."
        )
    )
    no_fill_price: int = Field(
        description="Chosen members whose trade had no price at the fill."
    )
    exits: int = Field(
        description="Holdings valued at their last close before their period ended."
    )


class CoverageRow(CoverageCounts):
    """A security's member-decisions in one year."""

    ticker: str | None = Field(
        description=(
            "Its ticker at its last decision that year that had one: null if it had "
            "stopped trading at every one."
        )
    )
    name: str
    year: int = Field(description="The New York calendar year of the decisions.")


class CoverageExit(_Model):
    """A holding valued at its last close before its period ended."""

    decision: date = Field(
        description="The New York day of the decision that chose it."
    )
    ticker: str = Field(description="Its ticker at that decision.")
    kind: ExitKind = Field(
        description=(
            '"delisted_exit" if it had stopped trading, after the spec\'s assumed '
            'delisting return, and "missing_price" if its bar at the period\'s end was '
            "missing."
        )
    )
    valued_at: PricePoint = Field(description="Its last close.")
    end: PricePoint = Field(
        description=(
            "Where its period ended: the next fill, where it was closed, or the run's "
            "last close."
        )
    )


class CoverageReport(_Model):
    """What data a run's decisions lacked, by security and year, and which holdings it
    valued at their last close (doc/reference/runs.md)."""

    decisions: int
    totals: CoverageCounts = Field(description="The rows added up.")
    rows: list[CoverageRow] = Field(
        description=(
            "One for each security and year it was a member at a decision, by "
            "security, then year."
        )
    )
    exits: list[CoverageExit] = Field(description="In decision order.")


class BacktestCoverage(_Model):
    run_id: str
    status: RunStatus
    coverage: CoverageReport | None = Field(
        description=(
            "Null until the run has succeeded, and for a run saved before engine "
            "1.1.0, which kept no coverage report."
        )
    )


def run_queue(request: Request) -> RunQueue:
    """The app's runs (see `create_app`)."""
    return request.app.state.run_queue


Runs = Annotated[RunQueue, Depends(run_queue)]


async def submitted_spec(request: Request) -> ExperimentSpec:
    """The request's body as a spec the engine can run, or a 422 that names each field
    as the spec's own errors do."""
    try:
        spec = parse_spec(await request.body())
        check_runnable(spec)
    except SpecError as error:
        raise _invalid(error.problems) from None
    except ScheduleError as error:
        problem = SpecProblem("schedule", schedule_problem(error))
        raise _invalid([problem]) from None
    return spec


def _invalid(problems: Iterable[SpecProblem]) -> RequestValidationError:
    """A 422 for a spec's problems, with their own sentences (app/api/errors.py)."""
    return RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", *problem.field.split(".")),
                "msg": problem.message,
                "input": None,
            }
            for problem in problems
        ]
    )


def known_job(run_id: str, runs: Runs) -> Job:
    """The run a path names, or a 404."""
    job = runs.get(run_id) if RUN_ID.fullmatch(run_id) else None
    if job is None:
        raise ApiError(404, "not_found", f"We have no run {run_id[:64]}.")
    return job


KnownJob = Annotated[Job, Depends(known_job)]

Decision = Annotated[
    date | None,
    Query(
        description=(
            "Only this decision's entries: the New York day of a decision, as in "
            "`result.periods`. Left out, every decision's."
        ),
        examples=["2020-06-01"],
    ),
]


@router.post(
    "",
    status_code=202,
    responses={
        200: {
            "model": BacktestSubmitted,
            "description": "This run is already saved: nothing was started",
        },
        202: {"description": "The run is queued, or was already in progress"},
        503: {
            "model": ErrorResponse,
            "description": "The queue is full, or this server can't save runs",
        },
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "description": (
                "An experiment spec (doc/reference/experiment-spec-v1.schema.json)."
            ),
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ExperimentSpec"},
                    "example": examples.CANONICAL_SPEC,
                }
            },
        }
    },
)
def submit_backtest(
    spec: Annotated[ExperimentSpec, Depends(submitted_spec)],
    runs: Runs,
    response: Response,
) -> BacktestSubmitted:
    """Submit an experiment spec. The run it names starts in the background, on the
    store's newest data version, unless it's already saved or in progress."""
    try:
        job = runs.submit(spec)
    except RunsUnavailableError as error:
        raise ApiError(503, "runs_unavailable", str(error)) from None
    if job.status == "succeeded":
        response.status_code = 200
    return BacktestSubmitted(run_id=job.run_id, status=job.status)


@router.get("/{run_id}", responses=examples.BACKTEST)
def get_backtest(job: KnownJob, settings: AppSettings) -> BacktestRun:
    """A run's status, and once it has succeeded, its metrics, its holding periods,
    its equity curve beside the benchmark's, and its warnings."""
    git_sha, result, hashed = None, None, spec_hash(job.spec)
    folder = saved_run(job.run_id, settings) if job.status == "succeeded" else None
    if folder is not None:
        manifest = read_document(folder, MANIFEST)
        # A run saved before engine 1.1.0 reads back with a delisting section its
        # spec didn't have, so its hash is the one it was saved with.
        git_sha, hashed = manifest["git_sha"], manifest["spec_hash"]
        returns = read_document(folder, "returns.json")
        result = BacktestResult(
            metrics=read_document(folder, "metrics.json"),
            periods=returns["periods"],
            equity_curve=returns["equity_curve"],
            warnings=read_document(folder, "warnings.json"),
        )
    progress = job.progress
    return BacktestRun(
        run_id=job.run_id,
        status=job.status,
        progress=(
            None
            if progress is None
            else BacktestProgress(
                decisions_done=progress.decisions_done,
                decisions_total=progress.decisions_total,
            )
        ),
        submitted_at=job.submitted_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        spec=job.spec,
        spec_hash=hashed,
        data_version=job.data_version,
        engine_version=job.engine_version,
        git_sha=git_sha,
        result=result,
    )


@router.get("/{run_id}/audit", responses=examples.BACKTEST_AUDIT)
def get_backtest_audit(
    job: KnownJob, settings: AppSettings, decision: Decision = None
) -> BacktestAudit:
    """What each view the run opened read, and when the newest of it became known:
    the evidence that no decision used anything from its future."""
    views = _entries(job, settings, "audit.json", decision)
    return BacktestAudit(run_id=job.run_id, status=job.status, views=views)


@router.get("/{run_id}/holdings", responses=examples.BACKTEST_HOLDINGS)
def get_backtest_holdings(
    job: KnownJob, settings: AppSettings, decision: Decision = None
) -> BacktestHoldings:
    """Each holding of each period: its weight, its signals' values at the decision,
    and its return."""
    holdings = _entries(job, settings, "holdings.json", decision)
    return BacktestHoldings(run_id=job.run_id, status=job.status, holdings=holdings)


@router.get("/{run_id}/trades", responses=examples.BACKTEST_TRADES)
def get_backtest_trades(
    job: KnownJob, settings: AppSettings, decision: Decision = None
) -> BacktestTrades:
    """Each trade at each fill: its weight before and after, and what it cost."""
    trades = _entries(job, settings, "trades.json", decision)
    return BacktestTrades(run_id=job.run_id, status=job.status, trades=trades)


@router.get("/{run_id}/coverage", responses=examples.BACKTEST_COVERAGE)
def get_backtest_coverage(job: KnownJob, settings: AppSettings) -> BacktestCoverage:
    """What data the run's decisions lacked, by security and year, and which holdings
    it valued at their last close: how far to trust its result (S6.7)."""
    folder = saved_run(job.run_id, settings) if job.status == "succeeded" else None
    coverage = None
    if folder is not None and (folder / "coverage.json").is_file():
        coverage = read_document(folder, "coverage.json")
    return BacktestCoverage(run_id=job.run_id, status=job.status, coverage=coverage)


def _entries(
    job: Job, settings: Settings, name: str, decision: date | None
) -> list[Any] | None:
    """One of a saved run's files that lists an entry for each decision's views,
    holdings, or trades: all of it, or one decision's. None for a run with no files
    yet."""
    folder = saved_run(job.run_id, settings) if job.status == "succeeded" else None
    if folder is None:
        return None
    entries = read_document(folder, name)
    if decision is None:
        return entries
    day = decision.isoformat()
    return [entry for entry in entries if entry["decision"] == day]
