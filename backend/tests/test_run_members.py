"""A run's members record (S9.6; doc/reference/runs.md), on runs made by hand: each
decision's members, their signals, the targets it chose, the holdings it got, and its
warnings, with no store.

tests/test_records.py checks the record a run of the loop saves, and
tests/test_simulation.py the signals and targets it's made from.
"""

import itertools
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.backtest.members import DecisionMember, summarize
from app.backtest.returns import PricePoint
from app.backtest.schedule import rebalances
from app.backtest.signals import SignalValue
from app.backtest.simulation import (
    DecisionMembers,
    Holding,
    HoldingPeriod,
    Simulation,
    SimulationWarning,
)
from app.backtest.spec import ExperimentSpec, parse_spec
from app.data.records import UniverseMember

CANONICAL = Path(__file__).parent / "fixtures" / "specs" / "canonical.json"


def spec(**changes: Any) -> ExperimentSpec:
    """The canonical spec from June to September 2020: rev_accel > 0, then
    mom_12_1 > 0, long only, with no ranking."""
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    data["period"] = {"start": "2020-06-01", "end": "2020-09-30"}
    return parse_spec(data | changes)


SPEC = spec()
SCHEDULE = rebalances(SPEC)
JUN_1, JUL_1, AUG_3, SEP_1 = (r.decision_time.date() for r in SCHEDULE)

RANKED = {
    "weighting": "equal",
    "long_only": True,
    "rank": {"signal": "mom_12_1", "quantiles": 2, "long": "top"},
}
"""A portfolio of the top half of a ranking by mom_12_1."""


def member(
    security_id: str, ticker: str | None, cik: int | None = None
) -> UniverseMember:
    """A member as a decision saw it, with no ticker once it had stopped trading."""
    return UniverseMember(
        universe="starter_large_caps",
        security_id=security_id,
        ticker=ticker,
        name=f"{security_id.title()} Inc.",
        cik=cik,
        added=date(2010, 1, 1),
        available_at=datetime(2010, 1, 1, 5, tzinfo=UTC),
        time_assumed=False,
        source="test",
        source_ref="made up",
    )


Values = Mapping[str, float | str]
"""A member's signals by ID: a value, or the reason it had none."""


@dataclass
class Decision:
    """What one decision saw and chose, and what the run then held."""

    members: Sequence[UniverseMember]
    values: Mapping[str, Values] = field(default_factory=dict)
    """By security ID. A trading member left out here has neither signal's value."""
    targets: Mapping[str, float] = field(default_factory=dict)
    held: Sequence[str] | None = ()
    """The security IDs held from its fill. None for a decision with no holding
    period: the run ended there."""


def signal_values(
    decision: Decision, run_spec: ExperimentSpec
) -> dict[str, dict[str, SignalValue]]:
    """Every spec signal's value for each trading member, as the loop records them."""
    found: dict[str, dict[str, SignalValue]] = {s: {} for s in run_spec.signals}
    for m in decision.members:
        if m.ticker is None:
            continue
        values = decision.values.get(m.security_id, {})
        for signal_id in run_spec.signals:
            answer = values.get(signal_id, "No value was known then.")
            found[signal_id][m.security_id] = (
                SignalValue(None, answer)
                if isinstance(answer, str)
                else SignalValue(answer)
            )
    return found


def a_run(
    decisions: Mapping[date, Decision],
    *,
    warnings: Sequence[SimulationWarning] = (),
    run_spec: ExperimentSpec = SPEC,
) -> Simulation:
    """A run of these decisions. Each with holdings gets a holding period that ends at
    the next fill."""
    periods = []
    for rebalance, following in itertools.pairwise([*SCHEDULE, SCHEDULE[-1]]):
        decision = decisions.get(rebalance.decision_time.date())
        if decision is None or decision.held is None:
            continue
        periods.append(
            HoldingPeriod(
                rebalance=rebalance,
                end=PricePoint(following.fill_session, following.fill_price),
                universe_size=len(decision.members),
                holdings=tuple(
                    Holding(
                        s,
                        s.upper(),
                        decision.targets[s],
                        {},
                        0.0,
                        PricePoint(following.fill_session, "close"),
                    )
                    for s in decision.held
                ),
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
                day,
                tuple(decision.members),
                signals=signal_values(decision, run_spec),
                targets=decision.targets,
            )
            for day, decision in decisions.items()
        ),
    )


def outcomes(found: Sequence[DecisionMember]) -> list[tuple[str, str, float | None]]:
    return [(m.security_id, m.outcome, m.weight) for m in found]


APPLE = member("apple", "AAPL", 320193)
ABBVIE = member("abbvie", "ABBV", 1551152)
PAYPAL = member("paypal", "PYPL", 1633917)
TWITTER = member("twitter", None, 1418091)


def test_every_member_gets_its_signals_and_an_outcome() -> None:
    june = Decision(
        members=(ABBVIE, APPLE, PAYPAL, TWITTER),
        values={
            "abbvie": {"mom_12_1": 0.13, "rev_accel": 0.053},
            "apple": {"mom_12_1": 0.62, "rev_accel": -0.0839},
            "paypal": {
                "mom_12_1": "Fewer than 12 months of prices were known.",
                "rev_accel": 0.0095,
            },
        },
        targets={"abbvie": 1.0},
        held=["abbvie"],
    )

    found = summarize(a_run({JUN_1: june}))

    assert outcomes(found) == [
        ("abbvie", "held", 1.0),
        ("apple", "failed_filter", None),
        ("paypal", "missing_signal", None),
        ("twitter", "stopped_trading", None),
    ]
    abbvie, apple, paypal, twitter = found
    assert apple == DecisionMember(
        decision=JUN_1,
        security_id="apple",
        ticker="AAPL",
        name="Apple Inc.",
        cik=320193,
        outcome="failed_filter",
        weight=None,
        signals={"mom_12_1": 0.62, "rev_accel": -0.0839},
        reasons={},
        missing=(),
        failed=(0,),  # rev_accel > 0, the spec's first filter
        rank=None,
    )
    assert abbvie.signals == {"mom_12_1": 0.13, "rev_accel": 0.053}
    assert (paypal.missing, paypal.failed) == (("mom_12_1",), ())
    assert paypal.reasons == {"mom_12_1": "Fewer than 12 months of prices were known."}
    # No signal was evaluated for a member that had stopped trading.
    assert twitter.signals == {"mom_12_1": None, "rev_accel": None}
    assert (twitter.reasons, twitter.missing, twitter.failed) == ({}, (), ())


def test_members_are_in_decision_order_then_as_the_decision_listed_them() -> None:
    both = {
        "abbvie": {"mom_12_1": 0.1, "rev_accel": 0.1},
        "apple": {"mom_12_1": 0.1, "rev_accel": 0.1},
    }
    targets = {"abbvie": 0.5, "apple": 0.5}
    decision = Decision((ABBVIE, APPLE), both, targets, held=["abbvie", "apple"])

    found = summarize(a_run({JUN_1: decision, JUL_1: decision}))

    assert [(m.decision, m.security_id) for m in found] == [
        (JUN_1, "abbvie"),
        (JUN_1, "apple"),
        (JUL_1, "abbvie"),
        (JUL_1, "apple"),
    ]


def test_a_member_lists_every_signal_it_lacked_and_every_filter_it_failed() -> None:
    decision = Decision(
        members=(ABBVIE, APPLE),
        values={"apple": {"mom_12_1": -0.2, "rev_accel": -0.01}},  # abbvie: neither
    )

    abbvie, apple = summarize(a_run({JUN_1: decision}))

    # The filters' signals in the spec's order, as the loop checks them.
    assert (abbvie.outcome, abbvie.missing) == (
        "missing_signal",
        ("rev_accel", "mom_12_1"),
    )
    assert abbvie.failed == ()  # a member left out isn't judged by the filters
    assert (apple.outcome, apple.failed) == ("failed_filter", (0, 1))


def test_a_choice_without_a_fill_price_isnt_held() -> None:
    decision = Decision(
        members=(ABBVIE, APPLE),
        values={
            "abbvie": {"mom_12_1": 0.1, "rev_accel": 0.1},
            "apple": {"mom_12_1": 0.1, "rev_accel": 0.1},
        },
        targets={"abbvie": 0.5, "apple": 0.5},
        held=["abbvie"],
    )
    unfilled = SimulationWarning("no_fill_price", JUN_1, "", "apple", "AAPL")

    found = summarize(a_run({JUN_1: decision}, warnings=[unfilled]))

    # It keeps the target it was chosen at.
    assert outcomes(found) == [("abbvie", "held", 0.5), ("apple", "no_fill_price", 0.5)]


def test_choices_at_a_decision_the_run_ended_on_werent_held() -> None:
    values = {"abbvie": {"mom_12_1": 0.1, "rev_accel": 0.1}}
    # June's period wiped the portfolio out at July's fill, after July's decision had
    # chosen: so July has members and targets, but no holding period.
    found = summarize(
        a_run(
            {
                JUN_1: Decision((ABBVIE,), values, {"abbvie": 1.0}, held=["abbvie"]),
                JUL_1: Decision((ABBVIE,), values, {"abbvie": 1.0}, held=None),
            }
        )
    )

    assert outcomes(found) == [("abbvie", "held", 1.0), ("abbvie", "wiped_out", 1.0)]


def test_a_ranking_places_every_member_that_passed() -> None:
    ranked_spec = spec(filters=[], portfolio=RANKED)
    gamma = member("gamma", "CCC")
    decision = Decision(
        members=(ABBVIE, APPLE, gamma, PAYPAL),
        values={
            "abbvie": {"mom_12_1": 0.1},
            "apple": {"mom_12_1": 0.3},
            "gamma": {"mom_12_1": 0.2},
            "paypal": {"rev_accel": 0.2},  # no mom_12_1, which the ranking needs
        },
        targets={"apple": 1.0},
        held=["apple"],
    )

    found = summarize(a_run({JUN_1: decision}, run_spec=ranked_spec))

    assert [(m.security_id, m.outcome, m.rank) for m in found] == [
        ("abbvie", "outside_ranking", 3),
        ("apple", "held", 1),
        ("gamma", "outside_ranking", 2),
        ("paypal", "missing_signal", None),
    ]
    # rev_accel had no value for them, but neither a filter nor the ranking needs it.
    assert found[1].missing == ()
    assert found[3].missing == ("mom_12_1",)


def test_a_short_is_held_at_its_negative_weight() -> None:
    long_short = spec(filters=[], portfolio=RANKED | {"long_only": False})
    decision = Decision(
        members=(ABBVIE, APPLE),
        values={"abbvie": {"mom_12_1": -0.3}, "apple": {"mom_12_1": 0.3}},
        targets={"abbvie": -1.0, "apple": 1.0},
        held=["abbvie", "apple"],
    )

    found = summarize(a_run({JUN_1: decision}, run_spec=long_short))

    assert outcomes(found) == [("abbvie", "held", -1.0), ("apple", "held", 1.0)]
    assert [m.rank for m in found] == [2, 1]


def test_a_long_short_ranking_of_one_holds_nothing() -> None:
    # A long-short portfolio needs a member at each end: with one, it holds cash.
    long_short = spec(filters=[], portfolio=RANKED | {"long_only": False})
    decision = Decision((APPLE,), {"apple": {"mom_12_1": 0.3}}, targets={}, held=[])

    (apple,) = summarize(a_run({JUN_1: decision}, run_spec=long_short))

    assert (apple.outcome, apple.weight, apple.rank) == ("outside_ranking", None, 1)


def test_an_empty_universe_has_no_members() -> None:
    assert summarize(a_run({JUN_1: Decision(members=(), held=[])})) == ()
