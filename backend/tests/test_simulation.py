"""The simulation loop (S7.3) on a toy market: three made-up stocks in the universe, and
SPY, from December 2020 through April 2021 (tests/toy_market.py).

Most tests use a scripted momentum signal in place of the signal library: at each
decision it answers from a script, so each test chooses the holdings, and it records
what the decision could see. One runs the canonical spec's signals from the library
itself (S7.4).

The ranked and long-short runs (S7.5) are worked by hand in
doc/reference/portfolio.md, which has the rules they check. So is the run whose
metrics are checked (S7.6), in doc/reference/metrics.md; tests/test_backtest_metrics.py
checks each metric on its own.
"""

import ast
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from app.backtest.metrics import equity_curve, summarize
from app.backtest.returns import PricePoint
from app.backtest.schedule import rebalances
from app.backtest.signals import SignalValue
from app.backtest.simulation import Simulation, SimulationWarning, simulate
from app.backtest.spec import ExperimentSpec, SpecError, parse_spec
from app.data import calendar
from app.data.records import UniverseMember
from app.data.tables import TABLES
from app.data.timeutil import ET
from app.data.versions import write_manifest
from app.data.view import PointInTimeView
from tests.toy_market import (
    INGESTED_AT,
    add_action,
    add_bars,
    add_member,
    add_release,
    add_revenue,
    add_security,
    steps,
)

ENGINE = Path(__file__).resolve().parents[1] / "app" / "backtest"
CANONICAL = Path(__file__).parent / "fixtures" / "specs" / "canonical.json"

START, END = date(2020, 12, 1), date(2021, 4, 30)
JAN_4, FEB_1, MAR_1, APR_1 = (
    date(2021, m, d) for m, d in ((1, 4), (2, 1), (3, 1), (4, 1))
)
"""The decisions: the first trading day of each month, at 09:30 ET."""

TICKERS = {"alpha": "AAA", "beta": "BBB", "gamma": "CCC", "spdr-sp500": "SPY"}
LEVELS = {
    # Closes on the fill days, January 4 to April 30: 100, 110, 99, 99, and 108.9.
    "alpha": {START: 100.0, date(2021, 1, 15): 110.0, date(2021, 2, 16): 99.0}
    | {date(2021, 4, 15): 108.9},
    # 100, 90, 90, 99, 99
    "beta": {START: 100.0, date(2021, 1, 15): 90.0, date(2021, 3, 15): 99.0},
    # 50, 50, 55, 55, 60.5
    "gamma": {START: 50.0, date(2021, 2, 16): 55.0, date(2021, 4, 15): 60.5},
    # Up 1% a month.
    "spdr-sp500": {START: 300.0, date(2021, 1, 15): 303.0, date(2021, 2, 16): 306.03}
    | {date(2021, 3, 15): 309.0903, date(2021, 4, 15): 312.181203},
}
"""Each security's close, which changes between fills, so a period's return is a
simple ratio."""

Script = Mapping[date, Mapping[str, float | str]]
"""The scripted signal's answers: at each decision, a value for each security, or the
reason it has none. A security left out gets -1, which fails `toy_spec`'s filter. A
spec without that filter would rank it last, so a ranking's script lists every one."""

CHOICES: Script = {
    JAN_4: {"alpha": 1.0, "beta": 1.0},
    FEB_1: {"alpha": 1.0, "gamma": 1.0},
    MAR_1: {"alpha": 1.0, "beta": 1.0, "gamma": 1.0},
    APR_1: {"gamma": 1.0},
}

Rates = Sequence[tuple[date, float, date]]
"""Releases of TB3MS, the risk-free rate: a month, its rate in percent a year, and the
day it came out, at 16:15 ET."""

LONG_KNOWN: Rates = [(date(2004, 12, 1), 1.2, date(2005, 1, 3))]
"""One rate, which every decision here knows, in 2009 too."""


def toy(
    store: Path,
    *,
    levels: Mapping[str, Mapping[date, float]] = LEVELS,
    skip: Mapping[str, Sequence[date]] | None = None,
    stopped: Mapping[str, date] | None = None,
    rates: Rates = LONG_KNOWN,
) -> Path:
    """The toy market, with a bar every session but the days in `skip`. A security in
    `stopped` stopped trading on that day: no bar from then on, and no ticker. `rates`
    are the risk-free rate's releases."""
    skip, stopped = skip or {}, stopped or {}
    for period, value, vintage in rates:
        add_release(store, "TB3MS", period, value, vintage)
    for security_id, ticker in TICKERS.items():
        until = stopped.get(security_id)
        last = END if until is None else calendar.previous_session(until)
        prices = steps(START, last, levels[security_id])
        for day in skip.get(security_id, ()):
            del prices[day]
        add_security(store, security_id, ticker, stopped=until)
        add_bars(store, security_id, prices)
    for security_id in ("alpha", "beta", "gamma"):
        add_member(store, security_id)
    return store


@pytest.fixture
def store(store_dir: Path) -> Path:
    return toy(store_dir)


def toy_spec(**changes: Any) -> ExperimentSpec:
    """The canonical spec (roadmap §3.4) over the toy market's months, January through
    April 2021, with one signal that must be positive, and `changes` merged in."""
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    data["period"] = {"start": "2021-01-01", "end": "2021-04-30"}
    data["signals"] = {
        "mom": {"type": "momentum", "lookback_months": 2, "skip_months": 0}
    }
    data["filters"] = [{"signal": "mom", "op": ">", "value": 0}]
    for key, value in changes.items():
        data[key] = data[key] | value if isinstance(value, dict) else value
    return parse_spec(data)


@dataclass
class Scripted:
    """A momentum signal that answers from a script. It records each decision's
    knowledge time, and the newest bar each member had then."""

    script: Script
    seen: list[tuple[datetime, dict[str, date | None]]] = field(default_factory=list)

    def __call__(
        self, view: PointInTimeView, members: Sequence[UniverseMember], params: Any
    ) -> dict[str, SignalValue]:
        newest = {}
        for member in members:
            assert member.ticker is not None
            bar = view.get_price_as_of(member.ticker)
            newest[member.security_id] = None if bar is None else bar.session_date
        self.seen.append((view.knowledge_time, newest))
        answers = self.script.get(view.knowledge_time.astimezone(ET).date(), {})
        found = {}
        for member in members:
            answer = answers.get(member.security_id, -1.0)
            found[member.security_id] = (
                SignalValue(None, answer)
                if isinstance(answer, str)
                else SignalValue(answer)
            )
        return found


def run(
    store: Path, script: Script = CHOICES, spec: ExperimentSpec | None = None
) -> Simulation:
    return simulate(
        toy_spec() if spec is None else spec,
        partial(PointInTimeView, store=store),
        signals={"momentum": Scripted(script)},
    )


def test_a_hand_checked_run(store: Path) -> None:
    result = run(store)
    jan, feb, mar, apr = result.periods

    assert [(p.rebalance.fill_session, p.end) for p in result.periods] == [
        (JAN_4, PricePoint(FEB_1, "close")),
        (FEB_1, PricePoint(MAR_1, "close")),
        (MAR_1, PricePoint(APR_1, "close")),
        (APR_1, PricePoint(END, "close")),
    ]
    assert {p.universe_size for p in result.periods} == {3}

    # January: half each in alpha and beta, bought from cash for 10 bps of it all.
    assert [(h.security_id, h.ticker, h.weight) for h in jan.holdings] == [
        ("alpha", "AAA", 0.5),
        ("beta", "BBB", 0.5),
    ]
    assert jan.holdings[0].signals == {"mom": 1.0}
    assert [h.period_return for h in jan.holdings] == [
        pytest.approx(0.1),
        pytest.approx(-0.1),
    ]
    assert (jan.turnover, jan.cost) == (1.0, pytest.approx(0.001))
    assert jan.gross_return == pytest.approx(0, abs=1e-15)
    assert jan.net_return == pytest.approx(-0.001)
    assert jan.value == pytest.approx(0.999)

    # February: alpha grew to 55%, so half of it is kept; beta is sold and gamma bought.
    assert [(t.security_id, t.weight_before, t.weight_after) for t in feb.trades] == [
        ("alpha", pytest.approx(0.55), 0.5),
        ("beta", pytest.approx(0.45), 0.0),
        ("gamma", 0.0, 0.5),
    ]
    assert (feb.turnover, feb.cost) == (pytest.approx(1.0), pytest.approx(0.001))
    assert feb.gross_return == pytest.approx(0, abs=1e-15)  # -10% and +10%
    assert feb.value == pytest.approx(0.999**2)

    # March: a third each, from 45% alpha and 55% gamma.
    turnover = (0.45 - 1 / 3) + 1 / 3 + (0.55 - 1 / 3)
    assert (mar.turnover, mar.cost) == (
        pytest.approx(turnover),
        pytest.approx(0.001 * turnover),
    )
    assert mar.gross_return == pytest.approx(0.1 / 3)  # beta's 10%
    assert mar.value == pytest.approx(0.999**2 * (1 - 0.001 * turnover) * (1 + 0.1 / 3))

    # April: all in gamma. Before the fill, beta had grown 10%, to 1.1 / 3.1 of it.
    before = {"alpha": 1 / 3.1, "beta": 1.1 / 3.1, "gamma": 1 / 3.1}
    assert [(t.security_id, t.weight_before, t.weight_after) for t in apr.trades] == [
        ("alpha", pytest.approx(before["alpha"]), 0.0),
        ("beta", pytest.approx(before["beta"]), 0.0),
        ("gamma", pytest.approx(before["gamma"]), 1.0),
    ]
    assert apr.turnover == pytest.approx(2 - 2 * before["gamma"])
    assert apr.gross_return == pytest.approx(0.1)
    assert apr.net_return == pytest.approx((1 - 0.001 * apr.turnover) * 1.1 - 1)

    # The value compounds the net returns, and SPY gained 1% a month.
    growth = 1.0
    for period in result.periods:
        growth *= 1 + period.net_return
        assert all(h.exit == period.end for h in period.holdings)
    assert apr.value == pytest.approx(growth)
    assert [p.benchmark_return for p in result.periods] == [pytest.approx(0.01)] * 4
    assert result.warnings == ()
    assert result.data_version is None  # the views read the whole store


def test_each_decision_sees_only_what_was_known_then(store: Path) -> None:
    signal = Scripted(CHOICES)
    simulate(
        toy_spec(), partial(PointInTimeView, store=store), signals={"momentum": signal}
    )

    schedule = rebalances(toy_spec())
    assert [moment for moment, _ in signal.seen] == [r.decision_time for r in schedule]
    for (_, newest), rebalance in zip(signal.seen, schedule, strict=True):
        # At 09:30 ET the newest bar is the previous session's. The store has the
        # day's own bar, but it isn't known until that day's close.
        day = rebalance.decision_time.astimezone(ET).date()
        assert set(newest.values()) == {calendar.previous_session(day)}


def test_the_engine_reads_only_through_its_view_factory(store: Path) -> None:
    events: list[tuple[str, datetime]] = []

    class Recorded(PointInTimeView):
        def close(self) -> None:
            events.append(("close", self.knowledge_time))
            super().close()

    def views(moment: datetime) -> PointInTimeView:
        events.append(("open", moment))
        return Recorded(moment, store=store)

    simulate(toy_spec(), views, signals={"momentum": Scripted(CHOICES)})

    # One view per decision at its time, and one at each fill session's close, when
    # the fill's bar became known; then the period's last close. Each is closed
    # before the next opens.
    moments = [
        moment
        for rebalance in rebalances(toy_spec())
        for moment in (
            rebalance.decision_time,
            calendar.session_close(rebalance.fill_session),
        )
    ]
    moments.append(calendar.session_close(END))
    assert events == [(kind, m) for m in moments for kind in ("open", "close")]


FORBIDDEN = ("duckdb", "pyarrow", "app.data.store", "app.data.versions", "app.config")
"""What the engine must never import: the store, its files, and where they are."""


def store_access(folder: Path, private: set[str]) -> list[str]:
    """Each line in the Python files under `folder`, in its packages too, that imports
    something FORBIDDEN or reads one of `private`, a view's private members, as
    "file:line" with the file's path from `folder`."""
    found = []
    for path in sorted(folder.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
            touches = isinstance(node, ast.Attribute) and node.attr in private
            if touches or any(
                name == banned or name.startswith(f"{banned}.")
                for name in names
                for banned in FORBIDDEN
            ):
                where = path.relative_to(folder).as_posix()
                found.append(f"{where}:{getattr(node, 'lineno', 0)}")
    return found


def private_members(store: Path) -> set[str]:
    """A view's private methods and attributes, such as `_select` and `_connection`."""
    with PointInTimeView(datetime(2021, 1, 4, tzinfo=UTC), store=store) as view:
        names = {*vars(PointInTimeView), *vars(view)}
    return {n for n in names if n.startswith("_") and not n.startswith("__")}


def test_the_engine_never_touches_the_store_itself(store_dir: Path) -> None:
    # The engine gets a view factory, never a store, a path to one, or a connection.
    private = private_members(store_dir)

    assert {"_select", "_connection"} <= private
    assert store_access(ENGINE, private) == []


@pytest.mark.parametrize(
    "line",
    [
        "import duckdb",
        "from app.data.store import connect",
        "from app.data import store",
        "from app.config import get_settings",
        "rows = view._select('price_bars')",
    ],
)
@pytest.mark.parametrize("where", ["portfolio.py", "signals/momentum.py"])
def test_the_store_guard_catches_an_offender(
    tmp_path: Path, store_dir: Path, line: str, where: str
) -> None:
    path = tmp_path / where
    path.parent.mkdir(exist_ok=True)
    path.write_text(f'"""Engine code."""\n{line}\n', encoding="utf-8")

    assert store_access(tmp_path, private_members(store_dir)) == [f"{where}:2"]


def test_next_day_open_fills(store_dir: Path) -> None:
    # Alpha is held throughout, bought and valued at opens: January 5, February 2,
    # March 2, and April 5, after Good Friday.
    prices = steps(
        START,
        END,
        {START: 100.0, date(2021, 1, 6): 101.0, date(2021, 2, 2): 99.0}
        | {date(2021, 3, 3): 50.0, date(2021, 4, 5): 52.0},
    )
    prices[date(2021, 1, 5)] = (100.0, 101.0)  # (open, close)
    prices[date(2021, 3, 2)] = (49.5, 50.0)  # the morning of a 2-for-1 split
    add_security(store_dir, "alpha", "AAA")
    add_member(store_dir, "alpha")
    add_bars(store_dir, "alpha", prices)
    add_action(store_dir, "alpha", date(2021, 2, 2), "dividend", 2.0)
    add_action(store_dir, "alpha", date(2021, 3, 2), "split", 2.0)
    add_security(store_dir, "spdr-sp500", "SPY")
    add_bars(store_dir, "spdr-sp500", steps(START, END, {START: 300.0}))
    add_release(store_dir, "TB3MS", *LONG_KNOWN[0])
    opened: list[datetime] = []

    def views(moment: datetime) -> PointInTimeView:
        opened.append(moment)
        return PointInTimeView(moment, store=store_dir)

    spec = toy_spec(schedule={"fill": "next_day_open"})
    script = {day: {"alpha": 1.0} for day in (JAN_4, FEB_1, MAR_1, APR_1)}
    result = simulate(spec, views, signals={"momentum": Scripted(script)})

    fills = [date(2021, 1, 5), date(2021, 2, 2), date(2021, 3, 2), date(2021, 4, 5)]
    assert [p.rebalance.fill_session for p in result.periods] == fills
    assert [p.end for p in result.periods] == [
        *(PricePoint(day, "open") for day in fills[1:]),
        PricePoint(END, "close"),
    ]
    assert [h.period_return for p in result.periods for h in p.holdings] == [
        # 101 / 100 on the first day, then (99 + 2) / 101 overnight: whoever held at
        # February 1's close gets the dividend, though the stock opens without it.
        pytest.approx(101 / 100 * (99 + 2) / 101 - 1),
        pytest.approx(2 * 49.5 / 99 - 1, abs=1e-15),  # the split, at March 2's open
        pytest.approx(50 / 49.5 * 52 / 50 - 1),
        pytest.approx(0, abs=1e-15),
    ]
    # Every view that values a fill is bound to the close of its session, when the
    # open's bar became known.
    assert opened[1::2] == [calendar.session_close(day) for day in fills]
    assert opened[-1] == calendar.session_close(END)
    assert [(p.turnover, p.cost) for p in result.periods] == [
        (1.0, pytest.approx(0.001)),
        *[(0, 0)] * 3,
    ]


@pytest.mark.parametrize(
    "after",
    [
        None,  # its bars just end
        (60.5, 0),  # a bar with no volume, repeating the last close: Twitter's end
        (61.0, 353),  # a leftover bar after Nasdaq halted it: Xilinx's end
    ],
)
def test_a_delisted_holding_is_exited_at_its_last_close(
    store_dir: Path, after: tuple[float, int] | None
) -> None:
    # Gamma stopped trading on March 11, at 60.5 after 55 on March 1, but stayed in
    # the universe. Whatever bar its vendor has from that day on, its last trade was
    # on March 10.
    levels = {**LEVELS, "gamma": {START: 50.0, date(2021, 2, 16): 55.0}}
    levels["gamma"] = levels["gamma"] | {date(2021, 3, 8): 60.5}
    toy(store_dir, levels=levels, stopped={"gamma": date(2021, 3, 11)})
    if after is not None:
        close, volume = after
        add_bars(store_dir, "gamma", {date(2021, 3, 11): close}, volume=volume)
    script = {
        JAN_4: {"alpha": 1.0},
        FEB_1: {"alpha": 1.0},
        MAR_1: {"alpha": 1.0, "gamma": 1.0},
        APR_1: {"alpha": 1.0, "gamma": 1.0},
    }

    result = run(store_dir, script)
    _, _, mar, apr = result.periods

    alpha, gamma = mar.holdings
    assert (alpha.period_return, alpha.exit) == (0.0, PricePoint(APR_1, "close"))
    assert gamma.exit == PricePoint(date(2021, 3, 10), "close")
    assert gamma.period_return == pytest.approx(0.1)
    assert mar.gross_return == pytest.approx(0.05)
    # It's sold at April's fill, at its last close's value, and costs as any sale.
    assert [(t.security_id, t.weight_before, t.weight_after) for t in apr.trades] == [
        ("alpha", pytest.approx(0.5 / 1.05), 1.0),
        ("gamma", pytest.approx(0.55 / 1.05), 0.0),
    ]
    assert apr.cost == pytest.approx(0.001 * 2 * 0.55 / 1.05)
    assert result.warnings == (
        SimulationWarning(
            "delisted_exit",
            MAR_1,
            "CCC stopped trading after 2021-03-10, so it was valued at that day's "
            "close, and sold at the next fill, on 2021-04-01.",
            "gamma",
            "CCC",
        ),
        SimulationWarning(
            "stopped_trading",
            APR_1,
            "CCC Corp. had stopped trading by the 2021-04-01 decision, so it was left "
            "out.",
            "gamma",
        ),
    )


ALPHA_THEN_BETA: Script = {
    JAN_4: {"alpha": 1.0},
    FEB_1: {"alpha": 1.0, "beta": 1.0},
    MAR_1: {"beta": 1.0},
    APR_1: {"beta": 1.0},
}


def test_a_missing_exit_price_values_a_holding_at_its_last_close(
    store_dir: Path,
) -> None:
    # Alpha has no bar on February 1, so it can't be valued or traded at that fill.
    toy(store_dir, skip={"alpha": [FEB_1]})

    jan, feb, *_ = run(store_dir, ALPHA_THEN_BETA).periods

    (alpha,) = jan.holdings
    assert alpha.exit == PricePoint(date(2021, 1, 29), "close")
    assert alpha.period_return == pytest.approx(0.1)
    assert [h.security_id for h in feb.holdings] == ["beta"]
    assert [(t.security_id, t.weight_after) for t in feb.trades] == [
        ("alpha", 0.0),
        ("beta", 0.5),
    ]
    assert feb.gross_return == pytest.approx(0, abs=1e-15)  # beta's flat February


def test_a_missing_exit_price_is_warned_about(store_dir: Path) -> None:
    toy(store_dir, skip={"alpha": [FEB_1]})

    warnings = run(store_dir, ALPHA_THEN_BETA).warnings

    assert warnings == (
        SimulationWarning(
            "missing_price",
            JAN_4,
            "AAA had no price at the close on 2021-02-01, so it was valued at its "
            "last close, on 2021-01-29, and sold at the next fill, on 2021-02-01.",
            "alpha",
            "AAA",
        ),
        SimulationWarning(
            "no_fill_price",
            FEB_1,
            "AAA had no price at the close on 2021-02-01, so it wasn't bought, and "
            "its share stayed in cash until the next fill.",
            "alpha",
            "AAA",
        ),
    )


@pytest.mark.parametrize("bar", [False, True])
def test_a_target_without_a_fill_price_stays_in_cash(
    store_dir: Path, bar: bool
) -> None:
    # Beta has no bar on February 1, the day its purchase would fill, or one for a
    # session in which nothing traded.
    toy(store_dir, skip={"beta": [FEB_1]})
    if bar:
        add_bars(store_dir, "beta", {FEB_1: 90.0}, volume=0)
    script = {
        JAN_4: {"alpha": 1.0},
        FEB_1: {"alpha": 1.0, "beta": 1.0},
        MAR_1: {"alpha": 1.0},
        APR_1: {"alpha": 1.0},
    }

    result = run(store_dir, script)
    feb = result.periods[1]

    assert [(h.security_id, h.weight) for h in feb.holdings] == [("alpha", 0.5)]
    assert feb.gross_return == pytest.approx(0.5 * -0.1)  # half of alpha's -10%
    assert result.warnings == (
        SimulationWarning(
            "no_fill_price",
            FEB_1,
            "BBB had no price at the close on 2021-02-01, so it wasn't bought, and "
            "its share stayed in cash until the next fill.",
            "beta",
            "BBB",
        ),
    )


def test_a_member_missing_a_signal_is_left_out(store: Path) -> None:
    reason = "Fewer than 2 months of prices were known."
    script = {
        JAN_4: {"alpha": 1.0, "beta": reason},
        FEB_1: {"alpha": 1.0, "beta": 1.0},
        MAR_1: {"alpha": 1.0},
        APR_1: {"alpha": 1.0},
    }

    result = run(store, script)

    jan, feb, *_ = result.periods
    assert [h.security_id for h in jan.holdings] == ["alpha"]
    assert [h.security_id for h in feb.holdings] == ["alpha", "beta"]
    (warning,) = result.warnings
    assert warning == SimulationWarning(
        "missing_signal",
        JAN_4,
        "BBB was left out at the 2021-01-04 decision, because mom had no value. "
        "Fewer than 2 months of prices were known.",
        "beta",
        "BBB",
        "mom",
    )


def test_an_empty_portfolio_holds_cash(store: Path) -> None:
    script = {JAN_4: {"alpha": 1.0}, MAR_1: {"alpha": 1.0}, APR_1: {"alpha": 1.0}}

    result = run(store, script)

    jan, feb, *_ = result.periods
    assert feb.holdings == ()
    assert [(t.security_id, t.weight_after) for t in feb.trades] == [("alpha", 0.0)]
    assert feb.gross_return == 0
    assert feb.value == pytest.approx(jan.value * (1 - feb.cost))
    assert result.warnings == (
        SimulationWarning(
            "empty_portfolio",
            FEB_1,
            "No member of starter_large_caps was chosen at the 2021-02-01 decision, "
            "so the portfolio held cash.",
        ),
    )


def test_an_empty_universe_holds_cash_without_a_benchmark(store: Path) -> None:
    # The universe starts in 2010 (D3), and the toy market's prices in December 2020.
    spec = toy_spec(period={"start": "2009-01-01", "end": "2009-02-27"})

    result = run(store, {}, spec)

    assert [(p.holdings, p.value, p.benchmark_return) for p in result.periods] == [
        ((), 1.0, None),
        ((), 1.0, None),
    ]
    assert [(w.kind, w.decision) for w in result.warnings] == [
        ("empty_portfolio", date(2009, 1, 2)),
        ("missing_benchmark", date(2009, 1, 2)),
        ("empty_portfolio", date(2009, 2, 2)),
        ("missing_benchmark", date(2009, 2, 2)),
    ]
    assert result.warnings[0].message == (
        "starter_large_caps had no members at the 2009-01-02 decision, so the "
        "portfolio held cash."
    )
    assert result.warnings[1].message == (
        "SPY, the benchmark, had no price for the period from the 2009-01-02 "
        "decision to 2009-02-02, so the period has no benchmark return."
    )


def test_a_decision_that_would_fill_after_the_end_is_skipped(store: Path) -> None:
    spec = toy_spec(period={"start": "2021-01-01", "end": "2021-02-01"})

    result = run(store, CHOICES, spec)

    assert [p.end for p in result.periods] == [PricePoint(FEB_1, "close")]
    assert result.warnings == (
        SimulationWarning(
            "fill_after_end",
            FEB_1,
            "The 2021-02-01 decision was skipped: its trades would fill at the close "
            "on 2021-02-01, but the period ends at the close on 2021-02-01.",
        ),
    )


DECISIONS = (JAN_4, FEB_1, MAR_1, APR_1)


def order(*security_ids: str) -> dict[str, float]:
    """A script's answers that rank the securities in this order: 0.3, 0.2, and 0.1
    for three, so each passes `toy_spec`'s filter."""
    count = len(security_ids)
    return {s: (count - place) / 10 for place, s in enumerate(security_ids)}


def ranked_spec(
    *, quantiles: int = 3, long: str = "top", long_only: bool = True, **changes: Any
) -> ExperimentSpec:
    """`toy_spec` with a ranking by its signal. By default it holds the top third,
    which is one of the three stocks."""
    rank = {"signal": "mom", "quantiles": quantiles, "long": long}
    return toy_spec(portfolio={"long_only": long_only, "rank": rank}, **changes)


def weights(result: Simulation) -> list[list[tuple[str, float]]]:
    """Each period's holdings and their weights."""
    return [[(h.security_id, h.weight) for h in p.holdings] for p in result.periods]


def test_a_hand_checked_ranked_run(store: Path) -> None:
    # A fourth stock, flat at 20 but for 10% in March, so half of the four is two.
    add_security(store, "delta", "DDD")
    add_bars(store, "delta", steps(START, END, {START: 20.0, date(2021, 3, 15): 22.0}))
    add_member(store, "delta")
    script = {
        JAN_4: order("alpha", "gamma", "beta", "delta"),
        # Beta fails the filter, so three are ranked, and half of three is one.
        FEB_1: order("gamma", "alpha", "delta") | {"beta": -0.1},
        MAR_1: order("beta", "delta", "alpha", "gamma"),
        APR_1: order("alpha", "gamma", "beta", "delta"),
    }

    result = run(store, script, ranked_spec(quantiles=2))
    jan, feb, mar, apr = result.periods

    assert {p.universe_size for p in result.periods} == {4}
    assert weights(result) == [
        [("alpha", 0.5), ("gamma", 0.5)],
        [("gamma", 1.0)],
        [("beta", 0.5), ("delta", 0.5)],
        [("alpha", 0.5), ("gamma", 0.5)],
    ]
    assert jan.holdings[0].signals == {"mom": 0.4}

    # January: the top half, bought from cash. Alpha gains 10%, and gamma nothing.
    assert (jan.turnover, jan.cost) == (1.0, pytest.approx(0.001))
    assert jan.gross_return == pytest.approx(0.05)
    assert jan.value == pytest.approx(0.999 * 1.05)

    # February: alpha grew to 0.55 of the 1.05, and all of it is sold for gamma.
    assert [(t.security_id, t.weight_before, t.weight_after) for t in feb.trades] == [
        ("alpha", pytest.approx(11 / 21), 0.0),
        ("gamma", pytest.approx(10 / 21), 1.0),
    ]
    assert feb.turnover == pytest.approx(22 / 21)
    assert feb.gross_return == pytest.approx(0.1)  # gamma's 10%

    # March and April: everything is sold for two others, which both gain 10%.
    for period in (mar, apr):
        assert (period.turnover, period.cost) == (
            pytest.approx(2.0),
            pytest.approx(0.002),
        )
        assert period.gross_return == pytest.approx(0.1)
    assert apr.value == pytest.approx(
        (0.999 * 1.05) * ((1 - 0.001 * 22 / 21) * 1.1) * (0.998 * 1.1) ** 2
    )
    assert result.warnings == ()


def test_a_hand_checked_long_short_run(store: Path) -> None:
    # Long the top third of the three stocks and short the bottom third: one each
    # (doc/reference/portfolio.md works this run through).
    script = {
        JAN_4: order("alpha", "gamma", "beta"),
        FEB_1: order("alpha", "gamma", "beta"),
        MAR_1: order("beta", "gamma", "alpha"),
        APR_1: order("gamma", "beta", "alpha"),
    }

    result = run(store, script, ranked_spec(long_only=False))
    jan, feb, mar, apr = result.periods

    assert weights(result) == [
        [("alpha", 1.0), ("beta", -1.0)],
        [("alpha", 1.0), ("beta", -1.0)],
        [("alpha", -1.0), ("beta", 1.0)],
        [("alpha", -1.0), ("gamma", 1.0)],
    ]

    # January: all of the portfolio is bought, and as much again sold short, for 10 bps
    # of both. Alpha's 10% gain and beta's 10% loss both pay.
    assert (jan.turnover, jan.cost) == (2.0, pytest.approx(0.002))
    assert [h.period_return for h in jan.holdings] == [
        pytest.approx(0.1),
        pytest.approx(-0.1),
    ]
    assert jan.gross_return == pytest.approx(0.2)
    assert jan.net_return == pytest.approx(0.998 * 1.2 - 1)
    assert jan.value == pytest.approx(1.1976)

    # February: the portfolio grew 20%, so both sides are short of their targets.
    # Alpha is 1.1 / 1.2 of it, and beta -0.9 / 1.2.
    assert [(t.security_id, t.weight_before, t.weight_after) for t in feb.trades] == [
        ("alpha", pytest.approx(11 / 12), 1.0),
        ("beta", pytest.approx(-3 / 4), -1.0),
    ]
    assert (feb.turnover, feb.cost) == (pytest.approx(1 / 3), pytest.approx(1 / 3000))
    assert feb.gross_return == pytest.approx(-0.1)  # alpha's -10%, with beta flat

    # March: the ends swap. The portfolio shrank to 0.9, so alpha is 0.9 / 0.9 of it,
    # and beta -1 / 0.9.
    assert [(t.security_id, t.weight_before, t.weight_after) for t in mar.trades] == [
        ("alpha", pytest.approx(1.0), -1.0),
        ("beta", pytest.approx(-10 / 9), 1.0),
    ]
    assert mar.turnover == pytest.approx(2 + 19 / 9)  # more than four times: 37 / 9
    assert mar.gross_return == pytest.approx(0.1)  # beta's 10%, with alpha flat

    # April: gamma replaces beta, which grew with the portfolio to 1.1 / 1.1 of it.
    # Alpha, flat, is -1 / 1.1, and is topped up.
    assert [(t.security_id, t.weight_before, t.weight_after) for t in apr.trades] == [
        ("alpha", pytest.approx(-10 / 11), -1.0),
        ("beta", pytest.approx(1.0), 0.0),
        ("gamma", 0.0, 1.0),
    ]
    assert apr.turnover == pytest.approx(23 / 11)
    assert apr.gross_return == pytest.approx(0, abs=1e-15)  # both gain 10%

    growth = 1.0
    for period in result.periods:
        assert period.cost == pytest.approx(0.001 * period.turnover)
        assert period.net_return == pytest.approx(
            (1 + period.gross_return) * (1 - period.cost) - 1
        )
        growth *= 1 + period.net_return
    assert apr.value == pytest.approx(growth)
    assert apr.value == pytest.approx(1.177888167267)
    assert [p.benchmark_return for p in result.periods] == [pytest.approx(0.01)] * 4
    assert result.warnings == ()


def test_filters_come_before_the_ranking(store: Path) -> None:
    # Gamma has the lowest value, but it fails the filter, so the bottom half of the
    # two that are ranked is beta.
    script = {day: {"alpha": 0.3, "beta": 0.2, "gamma": -0.1} for day in DECISIONS}

    result = run(store, script, ranked_spec(quantiles=2, long="bottom"))

    assert weights(result) == [[("beta", 1.0)]] * 4
    assert result.warnings == ()


def test_a_tie_in_the_ranking_goes_to_the_lower_security_id(store: Path) -> None:
    script = {day: {"gamma": 0.2, "beta": 0.2, "alpha": 0.2} for day in DECISIONS}

    result = run(store, script, ranked_spec(long_only=False))

    assert weights(result) == [[("alpha", 1.0), ("gamma", -1.0)]] * 4


def test_a_member_missing_the_rankings_signal_is_left_out(store: Path) -> None:
    # No filter needs the signal here: only the ranking does.
    reason = "Fewer than 2 months of prices were known."
    script: Script = {
        JAN_4: {"alpha": 0.3, "beta": reason, "gamma": 0.2},
        **dict.fromkeys(DECISIONS[1:], order("beta", "alpha", "gamma")),
    }

    result = run(store, script, ranked_spec(quantiles=2, filters=[]))

    assert weights(result)[:2] == [[("alpha", 1.0)], [("beta", 1.0)]]
    assert result.warnings == (
        SimulationWarning(
            "missing_signal",
            JAN_4,
            "BBB was left out at the 2021-01-04 decision, because mom had no value. "
            "Fewer than 2 months of prices were known.",
            "beta",
            "BBB",
            "mom",
        ),
    )


@pytest.mark.parametrize(
    ("long_only", "held", "what"),
    [
        (True, [("alpha", 1.0)], "the top one was held"),
        (
            False,
            [("alpha", 1.0), ("gamma", -1.0)],
            "the top one was held long and the bottom one short",
        ),
    ],
)
def test_a_ranking_with_fewer_members_than_quantiles_holds_one(
    store: Path, long_only: bool, held: list[tuple[str, float]], what: str
) -> None:
    # A fifth of three stocks rounds down to none, and a portfolio of none would say
    # nothing about the ranking.
    script = dict.fromkeys(DECISIONS, order("alpha", "beta", "gamma"))

    result = run(store, script, ranked_spec(quantiles=5, long_only=long_only))

    assert weights(result) == [held] * 4
    assert [(w.kind, w.decision) for w in result.warnings] == [
        ("thin_ranking", day) for day in DECISIONS
    ]
    assert result.warnings[0].message == (
        "Only 3 members of starter_large_caps could be ranked by mom at the "
        f"2021-01-04 decision, fewer than the ranking's 5 quantiles, so {what}."
    )


def test_a_long_short_portfolio_needs_two_members_to_rank(store: Path) -> None:
    script = {
        **dict.fromkeys(DECISIONS, order("alpha", "gamma", "beta")),
        FEB_1: {"alpha": 0.3},  # the others fail the filter
    }

    result = run(store, script, ranked_spec(long_only=False))

    feb = result.periods[1]
    assert feb.holdings == ()
    assert [(t.security_id, t.weight_after) for t in feb.trades] == [
        ("alpha", 0.0),
        ("beta", 0.0),
    ]
    assert feb.gross_return == 0
    assert result.warnings == (
        SimulationWarning(
            "empty_portfolio",
            FEB_1,
            "Only 1 member of starter_large_caps could be ranked by mom at the "
            "2021-02-01 decision, and a long-short portfolio needs 2, so the "
            "portfolio held cash.",
        ),
    )


def test_a_short_without_a_fill_price_isnt_opened(store_dir: Path) -> None:
    # Beta has no bar on February 1, the day it would be sold short.
    toy(store_dir, skip={"beta": [FEB_1]})
    script = {
        JAN_4: order("gamma", "beta", "alpha"),
        **dict.fromkeys(DECISIONS[1:], order("gamma", "alpha", "beta")),
    }

    result = run(store_dir, script, ranked_spec(quantiles=2, long_only=False))
    feb = result.periods[1]

    assert [(h.security_id, h.weight) for h in feb.holdings] == [("gamma", 1.0)]
    # Alpha, short, rose 10% in January while gamma was flat, so the portfolio was
    # worth 0.9: alpha is bought back, and gamma trimmed to all of what's left.
    assert [(t.security_id, t.weight_before, t.weight_after) for t in feb.trades] == [
        ("alpha", pytest.approx(-11 / 9), 0.0),
        ("gamma", pytest.approx(10 / 9), 1.0),
    ]
    assert feb.gross_return == pytest.approx(0.1)  # gamma's 10%, with nothing short
    assert result.warnings == (
        SimulationWarning(
            "no_fill_price",
            FEB_1,
            "BBB had no price at the close on 2021-02-01, so it wasn't sold short, "
            "and the portfolio went without it until the next fill.",
            "beta",
            "BBB",
        ),
    )


def test_a_delisted_short_is_bought_back_at_its_last_close(store_dir: Path) -> None:
    # Gamma stopped trading on March 11, at 60.5 after 55 on March 1, while the
    # portfolio was short it.
    gamma = {START: 50.0, date(2021, 2, 16): 55.0, date(2021, 3, 8): 60.5}
    toy(
        store_dir,
        levels={**LEVELS, "gamma": gamma},
        stopped={"gamma": date(2021, 3, 11)},
    )
    script = {
        JAN_4: order("alpha", "gamma", "beta"),
        FEB_1: order("alpha", "gamma", "beta"),
        MAR_1: order("alpha", "beta", "gamma"),
        APR_1: order("alpha", "beta"),
    }

    result = run(store_dir, script, ranked_spec(quantiles=2, long_only=False))
    _, _, mar, apr = result.periods

    _, short = mar.holdings
    assert (short.security_id, short.weight) == ("gamma", -1.0)
    assert short.exit == PricePoint(date(2021, 3, 10), "close")
    assert short.period_return == pytest.approx(0.1)
    assert mar.gross_return == pytest.approx(-0.1)  # its 10% rise is the short's loss
    # The portfolio is worth 0.9, so alpha is 1 / 0.9 of it and gamma -1.1 / 0.9.
    # Gamma is bought back at its last close's value, and beta sold short instead.
    assert [(t.security_id, t.weight_before, t.weight_after) for t in apr.trades] == [
        ("alpha", pytest.approx(10 / 9), 1.0),
        ("beta", 0.0, -1.0),
        ("gamma", pytest.approx(-11 / 9), 0.0),
    ]
    assert apr.turnover == pytest.approx(7 / 3)
    assert result.warnings == (
        SimulationWarning(
            "delisted_exit",
            MAR_1,
            "CCC stopped trading after 2021-03-10, so it was valued at that day's "
            "close, and bought back at the next fill, on 2021-04-01.",
            "gamma",
            "CCC",
        ),
        SimulationWarning(
            "stopped_trading",
            APR_1,
            "CCC Corp. had stopped trading by the 2021-04-01 decision, so it was left "
            "out.",
            "gamma",
        ),
    )


@pytest.mark.parametrize(
    ("alpha", "gamma"),
    [
        # Gamma triples: the short loses twice the portfolio, less alpha's 10% gain.
        (LEVELS["alpha"], 150.0),
        # Gamma doubles while alpha is flat: the short loses exactly all of it.
        ({START: 100.0}, 100.0),
    ],
)
def test_a_short_that_loses_everything_ends_the_run(
    store_dir: Path, alpha: Mapping[date, float], gamma: float
) -> None:
    # Gamma is sold short at 50 in January, and is at `gamma` by February's fill.
    levels = {
        **LEVELS,
        "alpha": alpha,
        "gamma": {START: 50.0, date(2021, 1, 15): gamma},
    }
    toy(store_dir, levels=levels)
    script = dict.fromkeys(DECISIONS, order("alpha", "beta", "gamma"))

    result = run(store_dir, script, ranked_spec(long_only=False))

    (jan,) = result.periods  # February's decision was made, but never traded
    assert weights(result) == [[("alpha", 1.0), ("gamma", -1.0)]]
    assert jan.holdings[1].period_return == pytest.approx(gamma / 50 - 1)
    assert jan.end == PricePoint(FEB_1, "close")
    assert (jan.gross_return, jan.net_return, jan.value) == (-1.0, -1.0, 0.0)
    assert result.warnings == (
        SimulationWarning(
            "wiped_out",
            JAN_4,
            "The portfolio had nothing left at the close on 2021-02-01: what it held "
            "since the 2021-01-04 decision lost all of its value, so the run ended "
            "there.",
        ),
    )


def test_trades_the_portfolio_cant_pay_for_end_the_run(store: Path) -> None:
    # At 2,400 bps, opening both sides costs 48% of the portfolio. Then beta, long,
    # loses 10% and alpha, short, gains 10%, which leaves 0.52 * 0.8 = 0.416.
    script = {
        JAN_4: order("beta", "gamma", "alpha"),
        **dict.fromkeys(DECISIONS[1:], order("alpha", "gamma", "beta")),
    }
    spec = ranked_spec(long_only=False, costs={"bps_per_trade": 2400})

    result = run(store, script, spec)

    (jan,) = result.periods
    assert jan.cost == pytest.approx(0.48)
    assert jan.gross_return == pytest.approx(-0.2)
    assert jan.value == pytest.approx(0.416)
    # Swapping the ends in February would trade 19 / 8 of alpha, from -1.1 / 0.8, and
    # 17 / 8 of beta, from 0.9 / 0.8: 4.5 times the portfolio, for 108% of it. The
    # 0.416 stands.
    assert result.warnings == (
        SimulationWarning(
            "wiped_out",
            FEB_1,
            "The 2021-02-01 decision's trades, at the close on 2021-02-01, would have "
            "cost 108% of the portfolio's value, so none was made, and the run ended "
            "there.",
        ),
    )


VARYING_SPY = {
    **LEVELS,
    # Up 2% in January, down 1%, up 3%, then up 1%.
    "spdr-sp500": {START: 300.0, date(2021, 1, 15): 306.0, date(2021, 2, 16): 302.94}
    | {date(2021, 3, 15): 312.0282, date(2021, 4, 15): 315.148482},
}

H15: Rates = [
    (date(2020, 11, 1), 1.2, date(2020, 12, 1)),
    (date(2020, 12, 1), 2.4, JAN_4),
    (date(2021, 1, 1), 0.6, FEB_1),
    (date(2021, 2, 1), 3.6, MAR_1),
    (date(2021, 3, 1), 12.0, APR_1),
]
"""A month's rate comes out on the next month's first business day, at 16:15 ET: after
that day's 09:30 decision, which still knows the month before's. April's decision is
the last, so none of them knows March's 12%."""


def test_each_period_carries_the_risk_free_rate_its_decision_knew(
    store_dir: Path,
) -> None:
    toy(store_dir, rates=H15)

    result = run(store_dir)

    # Not 2.4, 0.6, 3.6, and 12: each of those came out that afternoon.
    assert [p.risk_free_rate for p in result.periods] == [1.2, 2.4, 0.6, 3.6]
    assert result.warnings == ()


def test_a_rate_counts_from_its_release_time(store_dir: Path) -> None:
    # A decision at 16:15 ET, the minute H.15 comes out, knows that day's release. It
    # trades at the next open.
    toy(store_dir, rates=H15)
    schedule = {
        "decision": "first_trading_day 16:15 America/New_York",
        "fill": "next_day_open",
    }

    result = run(store_dir, spec=toy_spec(schedule=schedule))

    assert [p.risk_free_rate for p in result.periods] == [2.4, 0.6, 3.6, 12.0]


def test_a_period_without_a_risk_free_rate_is_warned_about(store_dir: Path) -> None:
    # The first rate comes out after January's decision, so only that one has none.
    toy(store_dir, rates=H15[1:])

    result = run(store_dir)

    assert [p.risk_free_rate for p in result.periods] == [None, 2.4, 0.6, 3.6]
    assert result.warnings == (
        SimulationWarning(
            "missing_risk_free",
            JAN_4,
            "TB3MS, the 3-month Treasury bill rate, had no value known at the "
            "2021-01-04 decision, so the risk-free rate for the period to 2021-02-01 "
            "was taken as 0.",
        ),
    )


def test_a_published_rate_of_zero_isnt_missing(store_dir: Path) -> None:
    toy(store_dir, rates=[(date(2020, 11, 1), 0.0, date(2020, 12, 1))])

    result = run(store_dir)

    assert [p.risk_free_rate for p in result.periods] == [0.0] * 4
    assert result.warnings == ()


def test_a_hand_checked_runs_metrics_match_the_worked_example(store_dir: Path) -> None:
    # The holdings of test_a_hand_checked_run, so its net returns, against a benchmark
    # and a risk-free rate that vary. doc/reference/metrics.md works each number
    # below by hand, to six places.
    toy(store_dir, levels=VARYING_SPY, rates=H15)

    result = run(store_dir)
    metrics = summarize(result)

    assert [p.net_return for p in result.periods] == pytest.approx(
        [-0.001, -0.001, 1469 / 45000, 15269 / 155000]
    )
    assert [p.benchmark_return for p in result.periods] == pytest.approx(
        [0.02, -0.01, 0.03, 0.01]
    )
    assert [p.risk_free_rate for p in result.periods] == [1.2, 2.4, 0.6, 3.6]
    assert (metrics.periods, metrics.start, metrics.end) == (
        4,
        PricePoint(JAN_4, "close"),
        PricePoint(END, "close"),
    )
    assert metrics.years == pytest.approx(116 / 365.25)
    worked = {
        "total_return": 0.132102,
        "cagr": 0.477986,
        "volatility": 0.162501,
        "sharpe": 2.298444,
        "max_drawdown": -0.001999,
        "turnover": 1.007168,
        "hit_rate": 0.75,
        "benchmark_total_return": 0.050495,
        "benchmark_cagr": 0.167786,
        "excess_return": 0.310199,
        "beta": 0.295384,
        "alpha": 0.329415,
        "mean_excess_return": 0.019789,
        "excess_t_stat": 0.831492,
    }
    assert {name: getattr(metrics, name) for name in worked} == pytest.approx(
        worked, abs=5e-7
    )
    assert [(p.at, p.value, p.benchmark) for p in equity_curve(result)] == [
        (PricePoint(JAN_4, "close"), 1.0, 1.0),
        (PricePoint(FEB_1, "close"), pytest.approx(0.999), pytest.approx(1.02)),
        (PricePoint(MAR_1, "close"), pytest.approx(0.998001), pytest.approx(1.0098)),
        (
            PricePoint(APR_1, "close"),
            pytest.approx(1.030580, abs=5e-7),
            pytest.approx(1.040094),
        ),
        (
            PricePoint(END, "close"),
            pytest.approx(1.132102, abs=5e-7),
            pytest.approx(1.050495, abs=5e-7),
        ),
    ]


REJECTED = [
    (
        "portfolio.weighting",
        {"portfolio": {"weighting": "value"}},
        (
            "portfolio.weighting must be 'equal' for now: value weights aren't "
            "supported yet."
        ),
    ),
    (
        "costs.bps_per_trade",
        {"costs": {"bps_per_trade": 5000}},
        (
            "costs.bps_per_trade must be less than 5,000: a rebalance can trade "
            "twice the portfolio's value, so higher costs could use all of it."
        ),
    ),
    (
        "costs.bps_per_trade",
        {
            "costs": {"bps_per_trade": 2500},
            "portfolio": {
                "long_only": False,
                "rank": {"signal": "mom", "quantiles": 3, "long": "top"},
            },
        },
        (
            "costs.bps_per_trade must be less than 2,500 for a long-short portfolio: "
            "swapping its long and short ends trades four times the portfolio's "
            "value, so higher costs could use all of it."
        ),
    ),
    (
        "period",
        {"period": {"start": "2021-01-01", "end": "2021-01-04"}},
        (
            "period must include a decision whose trades fill before its last "
            "close, on 2021-01-04."
        ),
    ),
    (
        "benchmark",
        {"benchmark": "NOPE"},
        (
            "benchmark must be a ticker in our data, but no security used NOPE at "
            "the 2021-01-04 decision."
        ),
    ),
]
"""A field the engine rejects, a spec change that it rejects for it, and its message.
What a spec can't say at all, such as a long-short portfolio without a ranking, is
rejected when it's parsed (tests/test_spec.py)."""


@pytest.mark.parametrize(
    ("field", "changes", "message"),
    REJECTED,
    ids=[
        "value weights",
        "long-only costs",
        "long-short costs",
        "no decision",
        "unknown benchmark",
    ],
)
def test_what_the_engine_cant_run_is_rejected(
    store: Path, field: str, changes: dict[str, Any], message: str
) -> None:
    spec = toy_spec(**changes)  # it parses: only the engine turns it down

    with pytest.raises(SpecError) as raised:
        run(store, CHOICES, spec)

    assert [(p.field, p.message) for p in raised.value.problems] == [(field, message)]


def test_a_signal_the_engine_lacks_is_rejected(store: Path) -> None:
    with pytest.raises(SpecError) as raised:
        simulate(toy_spec(), partial(PointInTimeView, store=store), signals={})

    assert [p.message for p in raised.value.problems] == [
        (
            "signals.mom.type 'momentum' can't be evaluated yet: the engine has no "
            "such signal."
        )
    ]


def test_the_canonical_specs_signals_run_in_the_loop(store_dir: Path) -> None:
    # The library's own signals, with nothing scripted (S7.4). All three stocks rise,
    # so their 12-1 momentum is positive, but only alpha's revenue growth accelerates:
    # 1%, 3%, 6%, then 10% over 2019. Beta's slows, and gamma files no revenue.
    rising = steps(
        date(2019, 12, 2),
        END,
        {date(2019, 12, 2): 100.0, date(2020, 6, 1): 110.0}
        | {date(2020, 10, 1): 121.0, date(2021, 1, 4): 133.1},
    )
    for security_id, ticker, cik in [
        ("alpha", "AAA", 1),
        ("beta", "BBB", 2),
        ("gamma", "CCC", None),
    ]:
        add_security(store_dir, security_id, ticker, cik=cik)
        add_member(store_dir, security_id)
        add_bars(store_dir, security_id, rising)
    add_security(store_dir, "spdr-sp500", "SPY")
    add_bars(store_dir, "spdr-sp500", steps(START, END, {START: 300.0}))
    add_release(store_dir, "TB3MS", *LONG_KNOWN[0])
    year = [date(2019, 3, 31), date(2019, 6, 30), date(2019, 9, 30), date(2019, 12, 31)]
    a_year_later = [day.replace(year=2020) for day in year]
    flat = dict.fromkeys(year, 100.0)
    add_revenue(store_dir, 1, flat | dict(zip(a_year_later, [101.0, 103, 106, 110])))
    add_revenue(store_dir, 2, flat | dict(zip(a_year_later, [110.0, 108, 105, 101])))
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    data["period"] = {"start": "2021-01-01", "end": "2021-04-30"}

    result = simulate(parse_spec(data), partial(PointInTimeView, store=store_dir))

    assert [[h.security_id for h in p.holdings] for p in result.periods] == [
        ["alpha"]
    ] * 4
    holdings = [p.holdings[0].signals for p in result.periods]
    # Until the 10-K for 2020 was accepted, on 2021-02-09, the latest quarter known
    # ended 2020-09-30: 6% growth after 3%. Then 10% after 6%.
    assert [h["rev_accel"] for h in holdings] == pytest.approx([0.03, 0.03, 0.04, 0.04])
    # From 100 to 121, then to 133.1, as the window moves past January 2021's rise.
    assert [h["mom_12_1"] for h in holdings] == pytest.approx(
        [0.21, 0.21, 0.331, 0.331]
    )
    assert [(w.kind, w.decision, w.ticker, w.signal) for w in result.warnings] == [
        ("missing_signal", day, "CCC", "rev_accel")
        for day in (JAN_4, FEB_1, MAR_1, APR_1)
    ]
    assert result.warnings[0].message == (
        "CCC was left out at the 2021-01-04 decision, because rev_accel had no value. "
        "No quarterly revenue was known then."
    )


def test_the_same_inputs_give_the_same_result(store: Path) -> None:
    version = write_manifest(store, TABLES.values(), now=INGESTED_AT)
    assert version is not None
    views = partial(PointInTimeView, data_version=version.data_version, store=store)

    first, second = (
        simulate(toy_spec(), views, signals={"momentum": Scripted(CHOICES)})
        for _ in range(2)
    )

    assert first == second
    assert first.data_version == version.data_version == "20261019T120000Z"


def test_every_view_must_read_the_same_data_version(store: Path) -> None:
    version = write_manifest(store, TABLES.values(), now=INGESTED_AT)
    assert version is not None
    versions = iter([None, version.data_version])

    def views(moment: datetime) -> PointInTimeView:
        return PointInTimeView(moment, data_version=next(versions), store=store)

    with pytest.raises(ValueError, match="read data version '20261019T120000Z' after"):
        simulate(toy_spec(), views, signals={"momentum": Scripted(CHOICES)})
