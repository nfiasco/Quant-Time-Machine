"""A run's coverage report (S6.7; doc/reference/runs.md), on runs made by hand: their
members, warnings, and holdings, with no store.

tests/test_records.py checks the report a run of the loop saves, and
tests/test_simulation.py the warnings it's made from.
"""

import itertools
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.backtest.coverage import CoverageExit, summarize
from app.backtest.returns import PricePoint
from app.backtest.schedule import rebalances
from app.backtest.simulation import (
    DecisionMembers,
    Holding,
    HoldingPeriod,
    Simulation,
    SimulationWarning,
    WarningKind,
)
from app.backtest.spec import ExperimentSpec, parse_spec
from app.data.records import UniverseMember

CANONICAL = Path(__file__).parent / "fixtures" / "specs" / "canonical.json"


def spec(**changes: Any) -> ExperimentSpec:
    """The canonical spec from December 2021 through March 2022, so its decisions span
    two years. Both its signals are needed: rev_accel reads fundamentals and mom_12_1
    prices."""
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    data["period"] = {"start": "2021-12-01", "end": "2022-03-31"}
    return parse_spec(data | changes)


SPEC = spec()
SCHEDULE = rebalances(SPEC)
DEC_1, JAN_3, FEB_1, MAR_1 = (r.decision_time.date() for r in SCHEDULE)


def member(security_id: str, ticker: str | None = None) -> UniverseMember:
    """A member as a decision saw it, with no ticker once it had stopped trading."""
    return UniverseMember(
        universe="starter_large_caps",
        security_id=security_id,
        ticker=ticker,
        name=f"{security_id.title()} Corp.",
        cik=None,
        added=date(2010, 1, 1),
        available_at=datetime(2010, 1, 1, 5, tzinfo=UTC),
        time_assumed=False,
        source="test",
        source_ref="made up",
    )


MEMBERS = (member("alpha", "AAA"), member("beta", "BBB"), member("gamma", "CCC"))
"""The universe at every decision but where a test says otherwise."""


def warning(
    kind: WarningKind, day: date, security_id: str, signal: str | None = None
) -> SimulationWarning:
    return SimulationWarning(kind, day, "", security_id, None, signal)


def a_run(
    *,
    members: dict[date, Sequence[UniverseMember]] | None = None,
    warnings: Sequence[SimulationWarning] = (),
    holdings: dict[date, Sequence[Holding]] | None = None,
    run_spec: ExperimentSpec = SPEC,
) -> Simulation:
    """A run of the four decisions, each with `members` (MEMBERS by default) and, for
    those in `holdings`, a holding period that ends at the next fill."""
    members = members or {}
    holdings = holdings or {}
    periods = []
    for rebalance, following in itertools.pairwise(SCHEDULE):
        held = holdings.get(rebalance.decision_time.date())
        if held is None:
            continue
        periods.append(
            HoldingPeriod(
                rebalance=rebalance,
                end=PricePoint(following.fill_session, following.fill_price),
                universe_size=3,
                holdings=tuple(held),
                trades=(),
                turnover=0.0,
                cost=0.0,
                gross_return=0.0,
                net_return=0.0,
                benchmark_return=None,
                risk_free_rate=None,
                value=1.0,
            )
        )
    return Simulation(
        spec=run_spec,
        data_version=None,
        periods=tuple(periods),
        warnings=tuple(sorted(warnings, key=lambda w: w.decision)),
        members=tuple(
            DecisionMembers(
                day, tuple(members.get(day, MEMBERS)), signals={}, targets={}
            )
            for day in (r.decision_time.date() for r in SCHEDULE)
        ),
    )


def holding(security_id: str, ticker: str, exit: PricePoint) -> Holding:
    return Holding(security_id, ticker, 1.0, {}, 0.0, exit)


def row(report: Any, security_id: str, year: int) -> Any:
    (found,) = [
        r for r in report.rows if (r.security_id, r.year) == (security_id, year)
    ]
    return found


def test_each_member_gets_a_row_for_each_year_in_order() -> None:
    report = summarize(a_run())

    assert report.decisions == 4
    assert [(r.security_id, r.year, r.member_decisions) for r in report.rows] == [
        ("alpha", 2021, 1),
        ("alpha", 2022, 3),
        ("beta", 2021, 1),
        ("beta", 2022, 3),
        ("gamma", 2021, 1),
        ("gamma", 2022, 3),
    ]
    assert all(r.left_out == 0 for r in report.rows)
    # Every kind of data and every signal the filters need is listed, gaps or not.
    assert report.totals.missing == {"fundamentals": 0, "prices": 0}
    assert report.totals.signals == {"rev_accel": 0, "mom_12_1": 0}
    assert report.totals.member_decisions == 12


def test_a_member_without_two_signals_is_left_out_once() -> None:
    # Beta had neither signal on February 1: one member-decision left out, which lacked
    # both kinds of data.
    report = summarize(
        a_run(
            warnings=[
                warning("missing_signal", FEB_1, "beta", "rev_accel"),
                warning("missing_signal", FEB_1, "beta", "mom_12_1"),
                warning("missing_signal", MAR_1, "beta", "rev_accel"),
            ]
        )
    )

    beta = row(report, "beta", 2022)
    assert (beta.member_decisions, beta.left_out) == (3, 2)
    assert beta.missing == {"fundamentals": 2, "prices": 1}
    assert beta.signals == {"rev_accel": 2, "mom_12_1": 1}
    assert report.totals.left_out == 2


def test_a_member_that_stopped_trading_is_left_out() -> None:
    # Gamma stopped trading in February, but stayed in the universe for March's
    # decision.
    stopped = (member("alpha", "AAA"), member("beta", "BBB"), member("gamma"))
    report = summarize(
        a_run(
            members={MAR_1: stopped},
            warnings=[warning("stopped_trading", MAR_1, "gamma")],
        )
    )

    gamma = row(report, "gamma", 2022)
    assert (gamma.left_out, gamma.stopped_trading) == (1, 1)
    assert gamma.missing == {"fundamentals": 0, "prices": 0}
    # Its ticker is the last it had that year.
    assert (gamma.ticker, gamma.name) == ("CCC", "Gamma Corp.")


def test_a_choice_without_a_fill_price_is_counted() -> None:
    report = summarize(a_run(warnings=[warning("no_fill_price", JAN_3, "alpha")]))

    assert row(report, "alpha", 2022).no_fill_price == 1
    assert row(report, "alpha", 2022).left_out == 0  # it was chosen
    assert report.totals.no_fill_price == 1


def test_exits_say_where_each_holding_was_valued() -> None:
    # Gamma, chosen on December 1, stopped trading after December 20, and alpha,
    # chosen on February 1, had no bar at March's fill.
    january_fill = PricePoint(date(2022, 1, 3), "close")
    report = summarize(
        a_run(
            holdings={
                DEC_1: [
                    holding("alpha", "AAA", january_fill),
                    holding("gamma", "CCC", PricePoint(date(2021, 12, 20), "close")),
                ],
                FEB_1: [
                    holding("alpha", "AAA", PricePoint(date(2022, 2, 28), "close"))
                ],
            },
            warnings=[
                warning("delisted_exit", DEC_1, "gamma"),
                warning("missing_price", FEB_1, "alpha"),
            ],
        )
    )

    assert report.exits == (
        CoverageExit(
            decision=DEC_1,
            security_id="gamma",
            ticker="CCC",
            kind="delisted_exit",
            valued_at=PricePoint(date(2021, 12, 20), "close"),
            end=january_fill,
        ),
        CoverageExit(
            decision=FEB_1,
            security_id="alpha",
            ticker="AAA",
            kind="missing_price",
            valued_at=PricePoint(date(2022, 2, 28), "close"),
            end=PricePoint(date(2022, 3, 1), "close"),
        ),
    )
    assert row(report, "gamma", 2021).exits == 1
    assert row(report, "alpha", 2021).exits == 0  # valued at the period's end
    assert row(report, "alpha", 2022).exits == 1
    assert report.totals.exits == 2


def test_only_the_signals_the_filters_and_ranking_need_are_listed() -> None:
    # A macro signal no filter uses has no gaps to count.
    unused = {"type": "macro_change", "series": "UNRATE", "releases": 3}
    signals = SPEC.model_dump(mode="json")["signals"] | {
        "unrate_3m": unused | {"change": "absolute"}
    }
    report = summarize(a_run(run_spec=spec(signals=signals)))

    assert report.totals.signals == {"rev_accel": 0, "mom_12_1": 0}
    assert report.totals.missing == {"fundamentals": 0, "prices": 0}


def test_a_spec_without_filters_needs_no_signal() -> None:
    report = summarize(a_run(run_spec=spec(filters=[])))

    assert (report.totals.signals, report.totals.missing) == ({}, {})
    assert report.totals.member_decisions == 12


def test_warnings_about_the_portfolio_arent_a_members_gap() -> None:
    benchmark = SimulationWarning("missing_benchmark", JAN_3, "", "spy", "SPY")
    empty = SimulationWarning("empty_portfolio", FEB_1, "")

    report = summarize(a_run(warnings=[benchmark, empty]))

    assert summarize(a_run()) == report
