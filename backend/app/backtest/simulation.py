"""The simulation loop: a spec's decisions, one at a time, each seeing only what was
known then (S7.3, S7.5).

`simulate(spec, views)` runs an experiment spec (app/backtest/spec.py) through the
decisions its schedule makes (app/backtest/schedule.py). It reads data only through
`views`, a factory that opens a `PointInTimeView` bound to a time, so it never sees the
store or a database connection. For each decision:

1. A view bound to the decision's time, 09:30 ET by default, gives the universe's
   members then. Each signal is evaluated for them through that view. The members
   that pass every filter get equal weights, or, if the spec has a ranking, the ones
   at its ends do: the long end's add up to 1, and a long-short portfolio's short
   end's to -1 (app/backtest/portfolio.py; doc/reference/portfolio.md). The same
   view gives the risk-free rate the decision knew, TB3MS as last published by then,
   which the period's record carries for the Sharpe ratio (S7.6;
   app/backtest/metrics.py).
2. A view bound to the close of the fill's session, when the fill's bar became known
   (doc/reference/time-model.md, rules 4 and 10), values each holding from the last
   fill to this one (`holding_return` in app/backtest/returns.py). Then the portfolio
   trades to its target and pays the spec's costs.
3. The portfolio holds until the next fill. After the last decision, it's valued at the
   close of the period's last session.

The portfolio starts at 1, in cash, and cash earns nothing. A short is a holding with
a negative weight: its security's return counts against the portfolio, what it was
sold for stays in cash, and borrowing it costs nothing. Missing data doesn't stop a
run: each gap becomes a warning that says what was assumed.

- A member that had stopped trading at a decision, or had no value for a filter's
  signal or the ranking's, is left out (`stopped_trading`, `missing_signal`).
- If no member is chosen, the portfolio holds cash (`empty_portfolio`). So does a
  long-short portfolio with one member to rank, which can't be both ends.
- A ranking of fewer members than it has quantiles holds one at each end
  (`thin_ranking`).
- A chosen security without a price at the fill isn't bought, and its share stays in
  cash, or isn't sold short, and the portfolio goes without it (`no_fill_price`).
- A holding whose bars end before its period does, because it stopped trading or a bar
  is missing, is valued at its last close and closed at the next fill
  (`delisted_exit`, `missing_price`).
- A portfolio with nothing left at a period's end, or worth less than a fill's trades
  would cost, ends the run there (`wiped_out`). Only shorts, or holdings that lose
  everything, can do that.

A price counts only from a session in which the security traded: not from a bar with
no volume, which repeats the last close, nor from a vendor's bar from the day the
security's curated history says it stopped trading on (app/backtest/returns.py).
- A period without the benchmark's prices has no benchmark return
  (`missing_benchmark`).
- A period whose decision knew no risk-free rate has none, and the metrics count it
  as 0 (`missing_risk_free`).
- A decision whose trades would fill after the period's last close is skipped
  (`fill_after_end`).

Results hold weights, returns, and dates, never prices: Tiingo's prices are for
internal use only (D2).
"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from app.backtest.portfolio import (
    Trade,
    equal_weights,
    passes,
    ranked_weights,
    trade_to_target,
)
from app.backtest.returns import PricePoint, fills_at_as_of, holding_return_as_of
from app.backtest.schedule import Rebalance, rebalances
from app.backtest.signals import SIGNALS, Signal, SignalValue
from app.backtest.spec import ExperimentSpec, SpecError, SpecProblem
from app.data import calendar
from app.data.errors import NotFoundError
from app.data.records import Security, UniverseMember
from app.data.timeutil import ET, to_utc
from app.data.view import PointInTimeView

ViewFactory = Callable[[datetime], PointInTimeView]
"""Opens a new `PointInTimeView` bound to an aware datetime: the engine's only way to
read data. The engine closes each view it opens. For a store pinned to a data version:

    functools.partial(PointInTimeView, data_version=..., store=...)
"""

WarningKind = Literal[
    "stopped_trading",
    "missing_signal",
    "empty_portfolio",
    "thin_ranking",
    "no_fill_price",
    "delisted_exit",
    "missing_price",
    "missing_benchmark",
    "missing_risk_free",
    "fill_after_end",
    "wiped_out",
]

RISK_FREE_SERIES = "TB3MS"
"""The macro series whose latest value known at a decision is the period's risk-free
rate: the 3-month Treasury bill rate, in percent a year."""

MAX_BPS_PER_TRADE = 5_000
"""Costs must stay below this. A long-only rebalance can trade up to twice the
portfolio's value, so 50% of that would use all of it."""

MAX_BPS_LONG_SHORT = 2_500
"""And below this for a long-short portfolio, which trades four times its value to
swap its ends. That's no guarantee: once its shorts have lost, its weights before a
fill have no bound, so each fill checks that the portfolio can pay for its trades."""


@dataclass(frozen=True)
class SimulationWarning:
    """Data the run did without, and what it assumed instead."""

    kind: WarningKind
    decision: date
    """The New York day of the decision it concerns. For a holding's exit, that's the
    decision that chose it."""
    message: str
    """A sentence that names the security, the day, and the assumption."""
    security_id: str | None = None
    ticker: str | None = None
    signal: str | None = None
    """The signal's ID in the spec, for `missing_signal`."""


@dataclass(frozen=True)
class Holding:
    """A security held from one fill to the next."""

    security_id: str
    ticker: str
    """Its ticker at the decision that chose it."""
    weight: float
    """Its weight after the fill, a fraction of the portfolio's value then. Negative
    for a short."""
    signals: Mapping[str, float]
    """Its signals' values at the decision, by ID. A signal without a value is left
    out."""
    period_return: float
    """The security's total return from the fill to `exit`: a short gains what it
    loses."""
    exit: PricePoint
    """Where it was valued: the period's end, or its last close if its bars ended
    first."""


@dataclass(frozen=True)
class HoldingPeriod:
    """A decision, its trades, and the portfolio it held until the next fill."""

    rebalance: Rebalance
    end: PricePoint
    """Where the period ends: the next fill, or, after the last decision, the close of
    the period's last session."""
    universe_size: int
    """How many members the universe had at the decision."""
    holdings: tuple[Holding, ...]
    """In security ID order."""
    trades: tuple[Trade, ...]
    turnover: float
    """The value traded at the fill, a fraction of the portfolio's value before trading
    (app/backtest/portfolio.py)."""
    cost: float
    """What the trades cost, a fraction of the portfolio's value before trading."""
    gross_return: float
    """The portfolio's return from just after the fill to the period's end."""
    net_return: float
    """Its return from just before the fill, so after costs: (1 + gross_return) *
    (1 - cost) - 1."""
    benchmark_return: float | None
    """The benchmark's total return between the same prices, or None without them."""
    risk_free_rate: float | None
    """The 3-month Treasury bill rate (TB3MS) as last published by the decision, in
    percent a year: 0.09 is 0.09%. None if it had no value then, and the metrics count
    the period's as 0 (app/backtest/metrics.py)."""
    value: float
    """The portfolio's value at the period's end. It starts at 1, and a period that
    leaves nothing ends at 0."""


@dataclass(frozen=True)
class Simulation:
    """A spec's run: its holding periods, in order, and what it did without."""

    spec: ExperimentSpec
    data_version: str | None
    """The data version every view read, or None if they read the whole store."""
    periods: tuple[HoldingPeriod, ...]
    """One for each decision that traded: fewer than the schedule's if the portfolio
    was wiped out."""
    warnings: tuple[SimulationWarning, ...]
    """In decision order."""


def simulate(
    spec: ExperimentSpec,
    views: ViewFactory,
    *,
    signals: Mapping[str, Signal] = SIGNALS,
) -> Simulation:
    """Run `spec`, reading data only through the views `views` opens.

    `signals` are the kinds of signal the run can evaluate, by `type`: the library's,
    unless a test passes its own. A portfolio with nothing left ends the run early,
    with a `wiped_out` warning. Raises SpecError, naming each field, for what the
    engine can't run yet, such as value weights or a signal it doesn't have; for a
    period with no decision that fills before its last close; and for a benchmark no
    security used at the first decision. Raises ScheduleError for a schedule whose
    fills can't follow their decisions (app/backtest/schedule.py).
    """
    _check_supported(spec, signals)
    end = _last_close(spec.period.end)
    run = _Run(spec, views, signals)
    schedule = []
    for rebalance in rebalances(spec):
        if _fill(rebalance).time < end.time:
            schedule.append(rebalance)
        else:
            run.skip(rebalance, end)
    if not schedule:
        raise SpecError(
            [
                SpecProblem(
                    "period",
                    "period must include a decision whose trades fill before its "
                    f"last close, on {end.session}.",
                )
            ]
        )
    for rebalance in schedule:
        run.step(rebalance)
        if run.ended:
            break
    else:
        run.finish(end)
    return run.result()


@dataclass
class _Position:
    """A security the portfolio holds, by value, between fills.

    One whose bars ended before its period did keeps its last close's value until the
    next fill. It has no price there either, so it's closed then, at that value.
    """

    ticker: str
    value: float
    """In the portfolio's units: it starts at 1. Negative for a short, which owes that
    much."""


@dataclass(frozen=True)
class _Choice:
    """A member a decision chose: its ticker then, and its signals' values."""

    ticker: str
    signals: dict[str, float]


@dataclass(frozen=True)
class _Decision:
    rebalance: Rebalance
    day: date
    """The decision's New York day."""
    universe_size: int
    chosen: dict[str, _Choice]
    """The members it holds, by security ID, in ID order."""
    targets: dict[str, float]
    """Each one's target weight, negative for a short, in the same order."""
    risk_free_rate: float | None
    """TB3MS as last published by then, in percent a year, or None without a value."""


@dataclass(frozen=True)
class _OpenPeriod:
    """A holding period whose end isn't known yet."""

    decision: _Decision
    fill: PricePoint
    weights: dict[str, float]
    """The holdings' target weights, after the securities that couldn't fill. Negative
    for a short."""
    trades: tuple[Trade, ...]
    turnover: float
    cost: float
    value_before: float
    """The portfolio's value just before the fill."""
    value_after: float
    """Its value just after, less the costs."""


class _Run:
    """The state of one `simulate` call."""

    def __init__(
        self, spec: ExperimentSpec, views: ViewFactory, signals: Mapping[str, Signal]
    ) -> None:
        self.spec = spec
        self.views = views
        self.signals = signals
        # The signals a member needs a value for: the filters', then the ranking's.
        required = [condition.signal for condition in spec.filters]
        if spec.portfolio.rank is not None:
            required.append(spec.portfolio.rank.signal)
        self.required_signals = list(dict.fromkeys(required))
        self.data_version: str | None = None
        self.viewed = False
        self.benchmark: Security | None = None
        self.positions: dict[str, _Position] = {}
        self.cash = 1.0
        self.open: _OpenPeriod | None = None
        self.ended = False  # once the portfolio is wiped out: no more decisions
        self.periods: list[HoldingPeriod] = []
        self.warnings: list[SimulationWarning] = []

    @contextmanager
    def view(self, moment: datetime) -> Iterator[PointInTimeView]:
        """A view bound to `moment`, from the factory, closed after use. Every view
        must read the same data version."""
        with self.views(moment) as view:
            if view.knowledge_time != to_utc(moment):
                raise ValueError(
                    "the view factory bound a view to "
                    f"{view.knowledge_time.isoformat()}, not {moment.isoformat()}"
                )
            if not self.viewed:
                self.data_version, self.viewed = view.data_version, True
            elif view.data_version != self.data_version:
                raise ValueError(
                    f"the view factory read data version {view.data_version!r} after "
                    f"{self.data_version!r}"
                )
            yield view

    def step(self, rebalance: Rebalance) -> None:
        """Make a decision, then value the last period's holdings at its fill and
        trade to its target."""
        decision = self.decide(rebalance)
        fill = _fill(rebalance)
        with self.view(calendar.session_close(rebalance.fill_session)) as view:
            if self.open is not None:
                self.close_period(view, fill, final=False)
            if not self.ended:
                self.trade(view, decision, fill)

    def finish(self, end: PricePoint) -> None:
        """Value the last period's holdings at the close of the period's last
        session."""
        with self.view(end.time) as view:
            self.close_period(view, end, final=True)

    def decide(self, rebalance: Rebalance) -> _Decision:
        """The members a decision chooses, and their target weights, from what was
        known at its time only."""
        day = rebalance.decision_time.astimezone(ET).date()
        universe = self.spec.universe.id
        with self.view(rebalance.decision_time) as view:
            if self.benchmark is None:
                self.benchmark = self.resolve_benchmark(view, day)
            risk_free = view.get_macro_as_of(RISK_FREE_SERIES)
            members = view.universe_as_of(universe)
            trading = []
            for member in members:
                if member.ticker is None:
                    self.warn(
                        "stopped_trading",
                        day,
                        f"{member.name} had stopped trading by the {day} decision, so "
                        "it was left out.",
                        member.security_id,
                    )
                else:
                    trading.append(member)
            values = {
                signal_id: self.evaluate(view, signal_id, params, trading)
                for signal_id, params in self.spec.signals.items()
            }

        passed = {}
        for member in trading:
            ticker = member.ticker
            assert ticker is not None
            found = {
                signal_id: values[signal_id][member.security_id] for signal_id in values
            }
            missing = [s for s in self.required_signals if found[s].value is None]
            for signal_id in missing:
                self.warn(
                    "missing_signal",
                    day,
                    f"{ticker} was left out at the {day} decision, because "
                    f"{signal_id} had no value. {found[signal_id].reason}",
                    member.security_id,
                    ticker,
                    signal_id,
                )
            known = {s: v.value for s, v in found.items() if v.value is not None}
            if missing or not all(
                passes(condition, known[condition.signal])
                for condition in self.spec.filters
            ):
                continue
            passed[member.security_id] = _Choice(ticker, known)
        targets = self.target_weights(passed, day, universe_size=len(members))
        chosen = {security_id: passed[security_id] for security_id in targets}
        rate = None if risk_free is None else risk_free.value
        return _Decision(rebalance, day, len(members), chosen, targets, rate)

    def target_weights(
        self, passed: Mapping[str, _Choice], day: date, *, universe_size: int
    ) -> dict[str, float]:
        """The target weights of the members that passed the filters at a decision,
        in security ID order: equal ones for them all, or for the ends of the spec's
        ranking of them."""
        universe, portfolio = self.spec.universe.id, self.spec.portfolio
        rank = portfolio.rank
        if rank is None:
            targets = equal_weights(sorted(passed))
        else:
            targets = ranked_weights(
                {s: choice.signals[rank.signal] for s, choice in passed.items()},
                quantiles=rank.quantiles,
                long=rank.long,
                long_only=portfolio.long_only,
            )
        count = f"{len(passed)} {'member' if len(passed) == 1 else 'members'}"

        if targets and rank is not None and len(passed) < rank.quantiles:
            other = "bottom" if rank.long == "top" else "top"
            held = (
                f"the {rank.long} one was held"
                if portfolio.long_only
                else f"the {rank.long} one was held long and the {other} one short"
            )
            self.warn(
                "thin_ranking",
                day,
                f"Only {count} of {universe} could be ranked by {rank.signal} at the "
                f"{day} decision, fewer than the ranking's {rank.quantiles} "
                f"quantiles, so {held}.",
            )
        if not targets:
            if not universe_size:
                why = f"{universe} had no members at the {day} decision"
            elif passed and rank is not None:  # one member, which can't be both ends
                why = (
                    f"Only {count} of {universe} could be ranked by {rank.signal} at "
                    f"the {day} decision, and a long-short portfolio needs 2"
                )
            else:
                why = f"No member of {universe} was chosen at the {day} decision"
            self.warn("empty_portfolio", day, f"{why}, so the portfolio held cash.")
        return targets

    def evaluate(
        self,
        view: PointInTimeView,
        signal_id: str,
        params: Any,
        members: Sequence[UniverseMember],
    ) -> Mapping[str, SignalValue]:
        """One signal's values for every member."""
        found = self.signals[params.type](view, members, params)
        if missing := [m.security_id for m in members if m.security_id not in found]:
            raise ValueError(
                f"signal {signal_id} ({params.type}) gave no value or reason for "
                f"{', '.join(missing)}"
            )
        return found

    def resolve_benchmark(self, view: PointInTimeView, day: date) -> Security:
        """The security the spec's benchmark ticker named at the first decision."""
        try:
            return view.resolve_ticker(self.spec.benchmark)
        except NotFoundError:
            raise SpecError(
                [
                    SpecProblem(
                        "benchmark",
                        "benchmark must be a ticker in our data, but no security used "
                        f"{self.spec.benchmark} at the {day} decision.",
                    )
                ]
            ) from None

    def trade(
        self, view: PointInTimeView, decision: _Decision, fill: PricePoint
    ) -> None:
        """Trade at `fill` to the decision's target, through a view bound to the close
        of the fill's session."""
        targets = dict(decision.targets)
        for security_id, choice in decision.chosen.items():
            if not fills_at_as_of(view, view.get_security(security_id), fill):
                short = targets.pop(security_id) < 0
                instead = (
                    "it wasn't sold short, and the portfolio went without it"
                    if short
                    else "it wasn't bought, and its share stayed in cash"
                )
                self.warn(
                    "no_fill_price",
                    decision.day,
                    f"{choice.ticker} had no price at the {fill.price} on "
                    f"{fill.session}, so {instead} until the next fill.",
                    security_id,
                    choice.ticker,
                )

        value_before = self.cash + sum(p.value for p in self.positions.values())
        assert value_before > 0  # or the run would have ended when the period closed
        tickers: dict[str, str | None] = {
            security_id: position.ticker
            for security_id, position in self.positions.items()
        }
        tickers.update({s: choice.ticker for s, choice in decision.chosen.items()})
        trades, turnover, cost = trade_to_target(
            {s: p.value / value_before for s, p in self.positions.items()},
            targets,
            bps_per_trade=self.spec.costs.bps_per_trade,
            fill=fill,
            tickers=tickers,
        )
        if cost >= 1:
            self.wipe_out(
                decision.day,
                f"The {decision.day} decision's trades, at the {fill.price} on "
                f"{fill.session}, would have cost {cost:.0%} of the portfolio's value, "
                "so none was made, and the run ended there.",
            )
            return
        value_after = value_before * (1 - cost)
        self.positions = {
            security_id: _Position(
                decision.chosen[security_id].ticker, weight * value_after
            )
            for security_id, weight in targets.items()
        }
        self.cash = value_after - sum(p.value for p in self.positions.values())
        self.open = _OpenPeriod(
            decision, fill, targets, trades, turnover, cost, value_before, value_after
        )

    def close_period(self, view: PointInTimeView, end: PricePoint, final: bool) -> None:
        """Value the open period's holdings at `end`, through a view bound to the close
        of its session, and record the period."""
        period = self.open
        assert period is not None
        day = period.decision.day
        holdings = []
        for security_id, position in self.positions.items():
            security = view.get_security(security_id)
            held = holding_return_as_of(view, security, period.fill, end)
            if held is None:
                raise RuntimeError(
                    f"{security_id} was bought at the {period.fill} fill, but its "
                    "price there is gone"
                )
            position.value *= 1 + held.value
            if not held.complete:
                short = period.weights[security_id] < 0
                self.warn_exit(position, security, held.exit, end, day, final, short)
            holdings.append(
                Holding(
                    security_id=security_id,
                    ticker=position.ticker,
                    weight=period.weights[security_id],
                    signals=period.decision.chosen[security_id].signals,
                    period_return=held.value,
                    exit=held.exit,
                )
            )

        value = self.cash + sum(p.value for p in self.positions.values())
        if value <= 0:
            value, self.positions, self.cash = 0.0, {}, 0.0
            self.wipe_out(
                day,
                f"The portfolio had nothing left at the {end.price} on {end.session}: "
                f"what it held since the {day} decision lost all of its value, so the "
                "run ended there.",
            )
        self.periods.append(
            HoldingPeriod(
                rebalance=period.decision.rebalance,
                end=end,
                universe_size=period.decision.universe_size,
                holdings=tuple(holdings),
                trades=period.trades,
                turnover=period.turnover,
                cost=period.cost,
                gross_return=value / period.value_after - 1,
                net_return=value / period.value_before - 1,
                benchmark_return=self.benchmark_return(view, period, end),
                risk_free_rate=self.risk_free_rate(period, end),
                value=value,
            )
        )
        self.open = None

    def benchmark_return(
        self, view: PointInTimeView, period: _OpenPeriod, end: PricePoint
    ) -> float | None:
        """The benchmark's return over the period, read by its ID like a holding."""
        benchmark = self.benchmark
        assert benchmark is not None
        try:
            security = view.get_security(benchmark.security_id)
        except NotFoundError:  # a ticker only SEC's file knows, which has no prices
            held = None
        else:
            held = holding_return_as_of(view, security, period.fill, end)
        if held is not None and held.complete:
            return held.value
        self.warn(
            "missing_benchmark",
            period.decision.day,
            f"{benchmark.ticker}, the benchmark, had no price for the period from the "
            f"{period.decision.day} decision to {end.session}, so the period has no "
            "benchmark return.",
            benchmark.security_id,
            benchmark.ticker,
        )
        return None

    def risk_free_rate(self, period: _OpenPeriod, end: PricePoint) -> float | None:
        """The risk-free rate the period's decision knew, in percent a year."""
        rate = period.decision.risk_free_rate
        if rate is None:
            self.warn(
                "missing_risk_free",
                period.decision.day,
                f"{RISK_FREE_SERIES}, the 3-month Treasury bill rate, had no value "
                f"known at the {period.decision.day} decision, so the risk-free rate "
                f"for the period to {end.session} was taken as 0.",
            )
        return rate

    def warn_exit(
        self,
        position: _Position,
        security: Security,
        last: PricePoint,
        end: PricePoint,
        day: date,
        final: bool,
        short: bool,
    ) -> None:
        """Warn that a holding was valued at its last close, before the period's end."""
        then = (
            f"until the period ended, on {end.session}"
            if final
            else f"and {'bought back' if short else 'sold'} at the next fill, on "
            f"{end.session}"
        )
        if security.ticker is None:
            kind: WarningKind = "delisted_exit"
            message = (
                f"{position.ticker} stopped trading after {last.session}, so it was "
                f"valued at that day's close, {then}."
            )
        else:
            kind = "missing_price"
            message = (
                f"{position.ticker} had no price at the {end.price} on {end.session}, "
                f"so it was valued at its last close, on {last.session}, {then}."
            )
        self.warn(kind, day, message, security.security_id, position.ticker)

    def wipe_out(self, day: date, message: str) -> None:
        """End the run: the portfolio has nothing left to trade with."""
        self.ended = True
        self.warn("wiped_out", day, message)

    def skip(self, rebalance: Rebalance, end: PricePoint) -> None:
        """Warn that a decision was skipped because it would fill too late."""
        day = rebalance.decision_time.astimezone(ET).date()
        fill = _fill(rebalance)
        self.warn(
            "fill_after_end",
            day,
            f"The {day} decision was skipped: its trades would fill at the "
            f"{fill.price} on {fill.session}, but the period ends at the close on "
            f"{end.session}.",
        )

    def warn(
        self,
        kind: WarningKind,
        day: date,
        message: str,
        security_id: str | None = None,
        ticker: str | None = None,
        signal: str | None = None,
    ) -> None:
        self.warnings.append(
            SimulationWarning(kind, day, message, security_id, ticker, signal)
        )

    def result(self) -> Simulation:
        return Simulation(
            spec=self.spec,
            data_version=self.data_version,
            periods=tuple(self.periods),
            warnings=tuple(sorted(self.warnings, key=lambda w: w.decision)),
        )


def _check_supported(spec: ExperimentSpec, signals: Mapping[str, Signal]) -> None:
    """Raise SpecError for each option the engine can't run yet."""
    problems = []
    if spec.portfolio.weighting != "equal":
        problems.append(
            SpecProblem(
                "portfolio.weighting",
                "portfolio.weighting must be 'equal' for now: value weights aren't "
                "supported yet.",
            )
        )
    for signal_id, params in spec.signals.items():
        if params.type not in signals:
            field = f"signals.{signal_id}.type"
            problems.append(
                SpecProblem(
                    field,
                    f"{field} '{params.type}' can't be evaluated yet: the engine has "
                    "no such signal.",
                )
            )
    if spec.portfolio.long_only:
        limit, whose, why = MAX_BPS_PER_TRADE, "", "a rebalance can trade twice"
    else:
        limit, whose = MAX_BPS_LONG_SHORT, " for a long-short portfolio"
        why = "swapping its long and short ends trades four times"
    if spec.costs.bps_per_trade >= limit:
        problems.append(
            SpecProblem(
                "costs.bps_per_trade",
                f"costs.bps_per_trade must be less than {limit:,}{whose}: {why} the "
                "portfolio's value, so higher costs could use all of it.",
            )
        )
    if problems:
        raise SpecError(problems)


def _fill(rebalance: Rebalance) -> PricePoint:
    """The price a decision's trades get."""
    return PricePoint(rebalance.fill_session, rebalance.fill_price)


def _last_close(end: date) -> PricePoint:
    """The close of the last session on or before `end`."""
    session = end if calendar.is_session(end) else calendar.previous_session(end)
    return PricePoint(session, "close")
