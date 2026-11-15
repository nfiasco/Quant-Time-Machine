"""A run's audit (S7.7): what each view the loop opened read, summarized from its
access log (app/backtest/audit.py).

The first tests summarize logs written by hand. The rest run the canonical spec's own
signals on a toy market (`canonical_market` in tests/toy_market.py) and check the
audit the loop kept.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import partial
from pathlib import Path

import pytest

from app.backtest.audit import (
    InputGroup,
    ViewInputs,
    row_line,
    rows_hash,
    summarize_inputs,
    timestamp,
)
from app.backtest.canonical import canonical_json
from app.backtest.schedule import rebalances
from app.backtest.simulation import Simulation, simulate
from app.backtest.spec import ExperimentSpec, parse_spec
from app.data import calendar
from app.data.timeutil import ET, market_time
from app.data.view import AccessRecord, PointInTimeView
from tests.toy_market import add_bars, canonical_market

CANONICAL = Path(__file__).parent / "fixtures" / "specs" / "canonical.json"

JUNE_1 = datetime(2020, 6, 1, 13, 30, tzinfo=UTC)


@dataclass
class Read:
    """A view that has returned `access_log`: all `summarize_inputs` looks at."""

    access_log: tuple[AccessRecord, ...]
    knowledge_time: datetime = JUNE_1


def bar(security_id: str, day: date, *, known: datetime | None = None) -> AccessRecord:
    close = known or datetime.combine(day, time(20), tzinfo=UTC)
    return AccessRecord(
        "price_bars", (security_id, day), close, f"bar {security_id} {day}"
    )


def fact(cik: int, accession: str, value: float, accepted: datetime) -> AccessRecord:
    key = (cik, accession, "us-gaap:Revenues", "USD", date(2020, 3, 31), 91, value)
    return AccessRecord("xbrl_facts", key, accepted, accession)


LOG = (
    bar("beta", date(2020, 5, 28)),
    bar("alpha", date(2020, 5, 28)),
    bar("alpha", date(2020, 5, 29)),
    fact(1, "0001-20-000001", 58.3e9, datetime(2020, 4, 30, 20, 30, tzinfo=UTC)),
    bar("alpha", date(2020, 5, 29)),  # read twice
)


def summarize(*records: AccessRecord) -> ViewInputs:
    return summarize_inputs(Read(records), "decision", date(2020, 6, 1))  # type: ignore[arg-type]


def test_a_views_inputs_are_summarized_by_table_and_by_group() -> None:
    inputs = summarize(*LOG)

    assert (inputs.purpose, inputs.decision) == ("decision", date(2020, 6, 1))
    assert inputs.knowledge_time == JUNE_1
    assert [table.table for table in inputs.tables] == ["price_bars", "xbrl_facts"]
    assert inputs.rows == 4  # the bar read twice counts once

    bars, facts = inputs.tables
    assert bars.rows == 3
    assert bars.earliest_available_at == datetime(2020, 5, 28, 20, tzinfo=UTC)
    assert bars.latest_available_at == datetime(2020, 5, 29, 20, tzinfo=UTC)
    assert bars.groups == (
        InputGroup(
            "alpha", 2, datetime(2020, 5, 29, 20, tzinfo=UTC), "bar alpha 2020-05-29"
        ),
        InputGroup(
            "beta", 1, datetime(2020, 5, 28, 20, tzinfo=UTC), "bar beta 2020-05-28"
        ),
    )
    # A company's facts are grouped by its CIK, and name the last filing known.
    assert facts.groups == (
        InputGroup(1, 1, datetime(2020, 4, 30, 20, 30, tzinfo=UTC), "0001-20-000001"),
    )


def test_a_row_is_hashed_as_its_key_its_available_at_and_its_source() -> None:
    assert row_line(bar("alpha", date(2020, 5, 29))) == (
        '["alpha","2020-05-29","2020-05-29T20:00:00Z","bar alpha 2020-05-29"]'
    )
    assert row_line(LOG[3]) == (
        '[1,"0001-20-000001","us-gaap:Revenues","USD","2020-03-31",91,58300000000.0,'
        '"2020-04-30T20:30:00Z","0001-20-000001"]'
    )
    assert timestamp(datetime(2020, 6, 1, 9, 30, tzinfo=ET)) == "2020-06-01T13:30:00Z"


def test_a_rows_line_is_canonical_json() -> None:
    known = datetime(2020, 4, 30, 20, 30, 0, 250, tzinfo=UTC)
    rows = [
        *LOG,
        fact(2, "0002-20-000001", -0.0, known),
        AccessRecord("securities", ("café", None, True, 1e-7), known, "été ✓"),
    ]

    for row in rows:
        values = [
            value.isoformat() if isinstance(value, date) else value for value in row.key
        ]
        assert row_line(row) == canonical_json(
            [*values, timestamp(row.available_at), row.source_ref]
        )
    assert row_line(rows[-2]).count("-0.0") == 0
    with pytest.raises(ValueError, match="Out of range float"):
        row_line(fact(3, "0003-20-000001", float("nan"), known))


def test_a_tables_hash_can_be_worked_out_from_its_rows() -> None:
    (bars, _) = summarize(*LOG).tables
    lines = [
        '["alpha","2020-05-28","2020-05-28T20:00:00Z","bar alpha 2020-05-28"]',
        '["alpha","2020-05-29","2020-05-29T20:00:00Z","bar alpha 2020-05-29"]',
        '["beta","2020-05-28","2020-05-28T20:00:00Z","bar beta 2020-05-28"]',
    ]

    assert bars.sha256 == hashlib.sha256("\n".join(lines).encode()).hexdigest()
    assert bars.sha256 == rows_hash(reversed(lines))


def test_the_order_rows_were_read_in_doesnt_matter() -> None:
    # The store gives rows that tie in any order, and a signal may read a row twice.
    assert summarize(*reversed(LOG)) == summarize(*LOG)
    assert summarize(*LOG, *LOG) == summarize(*LOG)


def test_a_different_row_changes_the_hash() -> None:
    (bars, _) = summarize(*LOG).tables
    later = datetime(2020, 5, 29, 20, 0, 1, tzinfo=UTC)
    restated = [*LOG[:2], bar("alpha", date(2020, 5, 29), known=later), LOG[3]]
    (changed, _) = summarize(*restated).tables

    assert changed.rows == bars.rows
    assert changed.sha256 != bars.sha256


def test_rows_that_became_known_together_have_one_latest() -> None:
    together = datetime(2020, 5, 29, 20, tzinfo=UTC)
    rows = [
        AccessRecord(
            "corporate_actions", ("alpha", date(2020, 5, 29), kind), together, ref
        )
        for kind, ref in (("split", "the split"), ("dividend", "the dividend"))
    ]

    (one,) = summarize(*rows).tables
    (other,) = summarize(*reversed(rows)).tables

    # The row whose line sorts last: "split" follows "dividend".
    assert one.groups == other.groups
    assert one.groups[0].latest_source_ref == "the split"


def test_a_view_that_read_nothing_has_no_tables() -> None:
    inputs = summarize()

    assert inputs.tables == ()
    assert inputs.rows == 0


def spec() -> ExperimentSpec:
    """The canonical spec (roadmap §3.4), over the toy market's four months."""
    data = json.loads(CANONICAL.read_text(encoding="utf-8"))
    data["period"] = {"start": "2021-01-01", "end": "2021-04-30"}
    return parse_spec(data)


def run(store: Path) -> Simulation:
    return simulate(spec(), partial(PointInTimeView, store=store))


@pytest.fixture
def result(store_dir: Path) -> Simulation:
    return run(canonical_market(store_dir))


def test_the_audit_has_an_entry_for_each_view_the_loop_opened(
    result: Simulation,
) -> None:
    schedule = rebalances(spec())
    days = [r.decision_time.astimezone(ET).date() for r in schedule]
    expected = []
    for rebalance, day in zip(schedule, days, strict=True):
        close = calendar.session_close(rebalance.fill_session)
        expected += [
            ("decision", day, rebalance.decision_time),
            ("fill", day, close),
        ]
    expected.append(("end", days[-1], calendar.session_close(date(2021, 4, 30))))

    assert len(schedule) == 4
    assert [(v.purpose, v.decision, v.knowledge_time) for v in result.audit] == expected


def test_nothing_in_the_audit_was_known_after_its_views_time(
    result: Simulation,
) -> None:
    # What S12.1 will check for every run.
    tables = [(view, table) for view in result.audit for table in view.tables]

    assert tables
    for view, table in tables:
        assert table.earliest_available_at <= table.latest_available_at
        assert table.latest_available_at <= view.knowledge_time
        assert table.rows == sum(group.rows for group in table.groups)
        assert table.latest_available_at == max(
            group.latest_available_at for group in table.groups
        )


def test_a_decisions_audit_lists_what_its_signals_read(result: Simulation) -> None:
    january = result.audit[0]
    tables = {table.table: table for table in january.tables}

    assert sorted(tables) == [
        "macro_observations",
        "price_bars",
        "securities",
        "universe_members",
        "xbrl_facts",
    ]
    # The risk-free rate, the three members, and each one's bars for momentum.
    assert [g.key for g in tables["macro_observations"].groups] == ["TB3MS"]
    assert tables["macro_observations"].groups[0].latest_source_ref == (
        "made up: TB3MS 2004-12-01 from 2005-01-03"
    )
    assert [(g.key, g.rows) for g in tables["universe_members"].groups] == [
        ("starter_large_caps", 3)
    ]
    assert [g.key for g in tables["price_bars"].groups] == ["alpha", "beta", "gamma"]
    # 12-1 momentum skips the month before the decision, so the newest bar that
    # January's read is November 30's.
    assert {g.latest_source_ref for g in tables["price_bars"].groups} == {
        f"made up: {name} 2020-11-30" for name in ("alpha", "beta", "gamma")
    }
    # Gamma files no revenue, so only two companies have facts.
    assert [g.key for g in tables["xbrl_facts"].groups] == [1, 2]


def test_the_audit_names_the_last_filing_each_decision_knew(result: Simulation) -> None:
    def newest_fact(view: ViewInputs) -> datetime:
        (facts,) = (t for t in view.tables if t.table == "xbrl_facts")
        return facts.groups[0].latest_available_at

    decisions = [view for view in result.audit if view.purpose == "decision"]
    third_quarter = market_time(date(2020, 9, 30) + timedelta(days=40), time(16, 30))
    fourth_quarter = market_time(date(2020, 12, 31) + timedelta(days=40), time(16, 30))

    # The fourth quarter's filing was accepted on February 9, 2021, after February's
    # decision and before March's.
    assert [newest_fact(view) for view in decisions] == [
        third_quarter,
        third_quarter,
        fourth_quarter,
        fourth_quarter,
    ]


def test_a_fills_audit_lists_the_bars_that_valued_the_holdings(
    result: Simulation,
) -> None:
    fills = [view for view in result.audit if view.purpose != "decision"]

    # Alpha is the only holding, and SPY the benchmark. The first fill only buys.
    for number, view in enumerate(fills):
        tables = {table.table: table for table in view.tables}
        assert "xbrl_facts" not in tables
        bars = [group.key for group in tables["price_bars"].groups]
        assert bars == (["alpha"] if number == 0 else ["alpha", "spdr-sp500"])


def test_a_row_known_only_after_a_decision_isnt_in_its_audit(tmp_path: Path) -> None:
    clean = canonical_market(tmp_path / "clean" / "store")
    poisoned = canonical_market(tmp_path / "poisoned" / "store")
    # A second version of alpha's December 31 bar, known a microsecond after
    # January's decision.
    decision = rebalances(spec())[0].decision_time
    add_bars(
        poisoned,
        "alpha",
        {date(2020, 12, 31): 121.0},
        known_at=decision + timedelta(microseconds=1),
    )

    before, after = run(clean), run(poisoned)

    assert after.audit[0] == before.audit[0]  # January's decision never saw it
    assert after.audit[2] != before.audit[2]  # February's did, as the bar's latest
    assert after.periods == before.periods  # the same price, so the same results


def test_the_same_run_gives_the_same_audit(store_dir: Path) -> None:
    store = canonical_market(store_dir)

    assert run(store).audit == run(store).audit
