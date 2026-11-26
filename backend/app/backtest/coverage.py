"""A run's coverage report: what data its decisions lacked, by security and year, and
which holdings it valued at their last close (S6.7; doc/reference/runs.md).

Free price data leaves out companies that stopped trading, and no survivorship-free
source is available to check it against (R1), so every run says where its own data
ran out. `summarize(simulation)` reduces a finished run, as `metrics.summarize` does: it
reads no data of its own and adds nothing to the audit.

- **A member-decision** is a member of the universe at a decision.
- **It's left out for lack of data** when the member had stopped trading
  (`stopped_trading`), or when a signal a filter or the ranking needs had no value
  (`missing_signal`). A member without two signals counts once.
- **`missing`** says which data it lacked, by what the signals read: prices,
  fundamentals, or a macro series (`DATA` in app/backtest/signals/). A member without
  two signals of different kinds counts once in each. **`signals`** counts each
  signal's own gaps.
- **`no_fill_price`** counts chosen members whose trade had no price at the fill.
- **`exits`** are holdings valued at their last close before their period ended: one
  that stopped trading (`delisted_exit`), after the spec's assumed delisting return,
  and one whose bar at the period's end was missing (`missing_price`).

Each row is a security and the New York calendar year of its decisions, so the years
before XBRL filled in show. The report has counts, dates, and price points, never a
price (D2).
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.backtest.returns import PricePoint
from app.backtest.signals import DATA
from app.backtest.simulation import Simulation, needed_signals
from app.data.timeutil import ET

ExitKind = Literal["delisted_exit", "missing_price"]


@dataclass(frozen=True)
class CoverageCounts:
    """Member-decisions, and the gaps in their data."""

    member_decisions: int
    left_out: int
    """Member-decisions left out for lack of data: the member had stopped trading, or a
    signal a filter or the ranking needs had no value."""
    stopped_trading: int
    missing: Mapping[str, int]
    """Member-decisions left out because a signal reading this data had no value, by
    "prices", "fundamentals", or "macro": the kinds the spec's needed signals read."""
    signals: Mapping[str, int]
    """Member-decisions at which each needed signal had no value, by its ID."""
    no_fill_price: int
    """Chosen members whose trade had no price at the fill."""
    exits: int
    """Holdings chosen then that were valued at their last close before their period
    ended."""


@dataclass(frozen=True)
class CoverageRow(CoverageCounts):
    """A security's member-decisions in one year."""

    security_id: str
    ticker: str | None
    """Its ticker at its last decision that year that had one: None if it had stopped
    trading at every one."""
    name: str
    """Its name at that decision."""
    year: int
    """The New York calendar year of the decisions."""


@dataclass(frozen=True)
class CoverageExit:
    """A holding valued at its last close before its period ended."""

    decision: date
    """The New York day of the decision that chose it."""
    security_id: str
    ticker: str
    """Its ticker at that decision."""
    kind: ExitKind
    """"delisted_exit" if it had stopped trading, and "missing_price" if its bar for
    the period's end was missing."""
    valued_at: PricePoint
    """Its last close."""
    end: PricePoint
    """Where its period ended: the next fill, where it was closed, or the run's last
    close."""


@dataclass(frozen=True)
class RunCoverage:
    """What data a run's decisions lacked."""

    decisions: int
    """How many decisions the run made."""
    totals: CoverageCounts
    """The rows added up."""
    rows: tuple[CoverageRow, ...]
    """One for each security and year it was a member at a decision, in security ID
    order, then by year."""
    exits: tuple[CoverageExit, ...]
    """In decision order, then security ID order."""


@dataclass
class _Tally:
    """One row's counts as they're added up."""

    member_decisions: int = 0
    left_out: int = 0
    stopped_trading: int = 0
    missing: Counter[str] = field(default_factory=Counter)
    signals: Counter[str] = field(default_factory=Counter)
    no_fill_price: int = 0
    exits: int = 0


def summarize(simulation: Simulation) -> RunCoverage:
    """`simulation`'s coverage report: its member-decisions by security and year, the
    ones left out for lack of data and what they lacked, and its exits at a last
    close."""
    spec = simulation.spec
    needed = needed_signals(spec)
    reads = {signal: DATA[spec.signals[signal].type] for signal in needed}
    kinds = sorted(set(reads.values()))

    rows: dict[tuple[str, int], _Tally] = {}
    names: dict[tuple[str, int], tuple[str | None, str]] = {}
    for entry in simulation.members:
        for member in entry.members:
            key = (member.security_id, entry.decision.year)
            rows.setdefault(key, _Tally()).member_decisions += 1
            if member.ticker is not None or key not in names:
                names[key] = (member.ticker, member.name)

    # Why each member-decision was left out: it had stopped trading, or the signals
    # it had no value for.
    stopped: set[tuple[date, str]] = set()
    lacking: defaultdict[tuple[date, str], set[str]] = defaultdict(set)
    exit_kinds: dict[tuple[date, str], ExitKind] = {}
    for warning in simulation.warnings:
        if warning.security_id is None:
            continue
        key = (warning.decision, warning.security_id)
        match warning.kind:
            case "stopped_trading":
                stopped.add(key)
            case "missing_signal":
                assert warning.signal is not None
                lacking[key].add(warning.signal)
            case "no_fill_price":
                _row(rows, key).no_fill_price += 1
            case "delisted_exit" | "missing_price":
                exit_kinds[key] = warning.kind
    for key in stopped | lacking.keys():
        tally = _row(rows, key)
        tally.left_out += 1
        if key in stopped:
            tally.stopped_trading += 1
        signals = lacking.get(key, set())
        tally.missing.update({reads[signal] for signal in signals})
        tally.signals.update(signals)

    exits = []
    for period in simulation.periods:
        day = period.rebalance.decision_time.astimezone(ET).date()
        for holding in period.holdings:
            if holding.exit == period.end:
                continue
            key = (day, holding.security_id)
            _row(rows, key).exits += 1
            exits.append(
                CoverageExit(
                    decision=day,
                    security_id=holding.security_id,
                    ticker=holding.ticker,
                    kind=exit_kinds[key],
                    valued_at=holding.exit,
                    end=period.end,
                )
            )

    found = []
    for security_id, year in sorted(rows):
        tally = rows[(security_id, year)]
        ticker, name = names[(security_id, year)]
        found.append(
            CoverageRow(
                member_decisions=tally.member_decisions,
                left_out=tally.left_out,
                stopped_trading=tally.stopped_trading,
                missing={kind: tally.missing[kind] for kind in kinds},
                signals={signal: tally.signals[signal] for signal in needed},
                no_fill_price=tally.no_fill_price,
                exits=tally.exits,
                security_id=security_id,
                ticker=ticker,
                name=name,
                year=year,
            )
        )
    return RunCoverage(
        decisions=len(simulation.members),
        totals=_totals(found, kinds, needed),
        rows=tuple(found),
        exits=tuple(exits),
    )


def _row(rows: dict[tuple[str, int], _Tally], key: tuple[date, str]) -> _Tally:
    """The tally of a member-decision's row, by its decision's day and security."""
    day, security_id = key
    return rows.setdefault((security_id, day.year), _Tally())


def _totals(
    rows: list[CoverageRow], kinds: list[str], needed: list[str]
) -> CoverageCounts:
    """The rows added up."""

    def total(field: str) -> int:
        return sum(getattr(row, field) for row in rows)

    return CoverageCounts(
        member_decisions=total("member_decisions"),
        left_out=total("left_out"),
        stopped_trading=total("stopped_trading"),
        missing={kind: sum(row.missing[kind] for row in rows) for kind in kinds},
        signals={signal: sum(row.signals[signal] for row in rows) for signal in needed},
        no_fill_price=total("no_fill_price"),
        exits=total("exits"),
    )
