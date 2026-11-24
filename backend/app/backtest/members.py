"""Every member of a run's universe at each of its decisions: its signals' values, and
whether the run held it, or why not (S9.6; doc/reference/runs.md).

A run's holdings say what it bought, and its warnings which members it left out for lack
of data. Neither says what a member that failed a filter scored, so nobody could see why
a decision passed over a company it knew about: why June 1, 2020's didn't buy Apple, for
one. `summarize(simulation)` reduces a finished run's members, as `coverage.summarize`
does: it reads no data of its own and adds nothing to the audit.

Each member gets one outcome, checked in the order the loop decides
(app/backtest/simulation.py):

1. `stopped_trading`: it had stopped trading by the decision, so no signal was
   evaluated for it.
2. `missing_signal`: a signal a filter or the ranking needs had no value (`missing`).
3. `failed_filter`: it had them all, but failed at least one filter (`failed`).
4. The decision chose it, at its target weight (`weight`):
   - `held` from the fill to the period's end;
   - `no_fill_price` if it had no price at the fill, so it was neither bought nor
     sold short;
   - `wiped_out` if the run ended at this decision, before its trades were made.
5. `outside_ranking`: it passed every filter, but the ranking didn't put it in an end
   the portfolio holds, or a long-short portfolio had too few members to rank.

Values are fractions, as everywhere in the engine: 0.01 is 1%. No member holds a price
(D2).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.backtest.portfolio import passes, ranked
from app.backtest.signals import SignalValue
from app.backtest.simulation import Simulation, needed_signals
from app.backtest.spec import ExperimentSpec
from app.data.timeutil import ET

Outcome = Literal[
    "held",
    "no_fill_price",
    "wiped_out",
    "outside_ranking",
    "failed_filter",
    "missing_signal",
    "stopped_trading",
]


@dataclass(frozen=True)
class DecisionMember:
    """A member of the universe at a decision, and what the decision made of it."""

    decision: date
    """The New York day of the decision."""
    security_id: str
    ticker: str | None
    """Its ticker at the decision: None if it had stopped trading."""
    name: str
    """Its name at the decision."""
    cik: int | None
    """Its SEC Central Index Key, which keys its XBRL facts in the run's audit. None for
    a security without one."""
    outcome: Outcome
    weight: float | None
    """Its target weight if the decision chose it, negative for a short, whether or not
    it was held. None for one the decision didn't choose."""
    signals: Mapping[str, float | None]
    """Its value for every signal in the spec, by ID: None for one it had no value for,
    and for every signal of a member that had stopped trading."""
    reasons: Mapping[str, str]
    """Why each signal it had no value for had none, by ID, as a sentence a page can
    show. Empty for a member that had stopped trading."""
    missing: tuple[str, ...]
    """The signals a filter or the ranking needs that it had no value for: the
    filters', then the ranking's."""
    failed: tuple[int, ...]
    """The filters it failed, by their place in the spec's `filters`, from 0."""
    rank: int | None
    """Its place in the ranking of the members that passed every filter, from 1 for
    the highest value of the ranking's signal. None without a ranking, and for a member
    that didn't pass."""


def summarize(simulation: Simulation) -> tuple[DecisionMember, ...]:
    """Every member of `simulation`'s universe at each decision, in decision order,
    then security ID order, with its signals and what the decision made of it."""
    spec = simulation.spec
    needed = needed_signals(spec)
    rank = spec.portfolio.rank
    traded: set[date] = set()
    held: set[tuple[date, str]] = set()
    for period in simulation.periods:
        day = period.rebalance.decision_time.astimezone(ET).date()
        traded.add(day)
        held.update((day, holding.security_id) for holding in period.holdings)
    unfilled = {
        (warning.decision, warning.security_id)
        for warning in simulation.warnings
        if warning.kind == "no_fill_price"
    }

    found = []
    for entry in simulation.members:
        day = entry.decision
        judged = {
            member.security_id: _judge(entry.signals, member.security_id, spec, needed)
            for member in entry.members
            if member.ticker is not None
        }
        places: dict[str, int] = {}
        if rank is not None:
            passed = {
                security_id: _known(judgment.signals, rank.signal)
                for security_id, judgment in judged.items()
                if not judgment.missing and not judgment.failed
            }
            places = {s: place for place, s in enumerate(ranked(passed), start=1)}

        for member in entry.members:
            security_id = member.security_id
            weight = entry.targets.get(security_id)
            judgment = judged.get(security_id, _Judgment.stopped(spec.signals))
            outcome: Outcome
            if member.ticker is None:
                outcome = "stopped_trading"
            elif judgment.missing:
                outcome = "missing_signal"
            elif judgment.failed:
                outcome = "failed_filter"
            elif weight is None:
                outcome = "outside_ranking"
            elif (day, security_id) in held:
                outcome = "held"
            elif (day, security_id) in unfilled:
                outcome = "no_fill_price"
            else:
                # Chosen, but its trade was never made: the run ended at this decision.
                assert day not in traded, f"{security_id} was chosen on {day}, not held"
                outcome = "wiped_out"
            found.append(
                DecisionMember(
                    decision=day,
                    security_id=security_id,
                    ticker=member.ticker,
                    name=member.name,
                    cik=member.cik,
                    outcome=outcome,
                    weight=weight,
                    signals=judgment.signals,
                    reasons=judgment.reasons,
                    missing=judgment.missing,
                    failed=judgment.failed,
                    rank=places.get(security_id),
                )
            )
    return tuple(found)


@dataclass(frozen=True)
class _Judgment:
    """A member's signals at a decision, and whether it had what it needed and passed
    every filter."""

    signals: dict[str, float | None]
    reasons: dict[str, str]
    missing: tuple[str, ...]
    failed: tuple[int, ...]

    @classmethod
    def stopped(cls, signal_ids: Iterable[str]) -> _Judgment:
        """A member that had stopped trading, for which no signal was evaluated."""
        return cls({signal_id: None for signal_id in signal_ids}, {}, (), ())


def _judge(
    signals: Mapping[str, Mapping[str, SignalValue]],
    security_id: str,
    spec: ExperimentSpec,
    needed: Sequence[str],
) -> _Judgment:
    """A trading member's judgment: its values, the needed signals it lacked, and, if
    it lacked none, every filter it failed, as the loop's `passes` decides."""
    found = {signal_id: signals[signal_id][security_id] for signal_id in spec.signals}
    values = {signal_id: value.value for signal_id, value in found.items()}
    reasons = {
        signal_id: value.reason
        for signal_id, value in found.items()
        if value.reason is not None
    }
    missing = tuple(signal_id for signal_id in needed if values[signal_id] is None)
    failed: tuple[int, ...] = ()
    if not missing:
        failed = tuple(
            place
            for place, condition in enumerate(spec.filters)
            if not passes(condition, _known(values, condition.signal))
        )
    return _Judgment(values, reasons, missing, failed)


def _known(signals: Mapping[str, float | None], signal_id: str) -> float:
    """A needed signal's value, which a member that wasn't left out always has."""
    value = signals[signal_id]
    assert value is not None  # or it would have been missing
    return value
