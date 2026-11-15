"""A run's audit: what each view it opened read, and when each row became known (S7.7;
doc/reference/runs.md).

Every row a `PointInTimeView` returns goes in its access log (app/data/view.py). The
loop summarizes that log as each view closes (app/backtest/simulation.py), and keeps
the summary, not the rows: one decision of the canonical spec reads about 17,700 rows,
so sixteen years of them are about 3 million.

`summarize_inputs(view, purpose, decision)` gives a view's `ViewInputs`. For each table
it read:

- how many distinct rows, and the earliest and latest `available_at` among them. The
  latest is never after the view's knowledge time, which is what a reviewer checks;
- a SHA-256 of every distinct row, so a re-run can prove it read exactly the same
  ones (`row_line` and `rows_hash` say how it's computed);
- a group for each value of the table's first key column, such as a security, a
  company's CIK, or a macro series, with its newest row's `available_at` and
  `source_ref`: for a company's XBRL facts, the accession number of the last filing
  the decision knew.

A row read twice counts once, and the order the rows were read in doesn't matter: the
store gives rows that tie in any order.
"""

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from app.data.timeutil import to_utc
from app.data.view import AccessRecord, PointInTimeView

Purpose = Literal["decision", "fill", "end"]
"""What the loop opened a view for.

- `decision`: bound to a decision's time. The universe, the signals, the benchmark's
  identity, and the risk-free rate are read through it.
- `fill`: bound to the close of a decision's fill session. It values the holdings of
  the period that ends there, and checks which of the decision's choices can fill.
- `end`: bound to the close of the run's last session, to value the last period.
"""

GroupKey = str | int | float | bool | None

_ROW = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))
"""Writes a row's line. It's canonical JSON (app/backtest/canonical.py) without the
checks: a list has no keys to sort, and `_plain` has already made each value one of
JSON's own. A full run writes about three million of them, and a test keeps the two
the same."""


@dataclass(frozen=True)
class InputGroup:
    """One table's rows that share their first key column."""

    key: GroupKey
    """That column's value: a security ID in `price_bars`, a CIK in `xbrl_facts`, a
    series ID in `macro_observations`, a universe's name in `universe_members`."""
    rows: int
    latest_available_at: datetime
    """When the newest of its rows became known, in UTC."""
    latest_source_ref: str
    """That row's `source_ref`."""


@dataclass(frozen=True)
class TableInputs:
    """The rows a view returned from one table."""

    table: str
    rows: int
    """How many distinct rows: one read twice counts once."""
    earliest_available_at: datetime
    latest_available_at: datetime
    """When the newest of them became known, in UTC: never after the view's knowledge
    time."""
    sha256: str
    """`rows_hash` of them all."""
    groups: tuple[InputGroup, ...]
    """In key order."""


@dataclass(frozen=True)
class ViewInputs:
    """Everything one view returned to the loop."""

    purpose: Purpose
    decision: date
    """The New York day of the decision the view served. For `end`, the last
    decision's."""
    knowledge_time: datetime
    """The time the view was bound to, in UTC."""
    tables: tuple[TableInputs, ...]
    """The tables it returned rows from, in name order."""

    @property
    def rows(self) -> int:
        return sum(table.rows for table in self.tables)


def summarize_inputs(
    view: PointInTimeView, purpose: Purpose, decision: date
) -> ViewInputs:
    """What `view` has returned so far, from its access log."""
    by_table: dict[str, set[AccessRecord]] = {}
    for record in view.access_log:
        by_table.setdefault(record.table, set()).add(record)
    return ViewInputs(
        purpose=purpose,
        decision=decision,
        knowledge_time=view.knowledge_time,
        tables=tuple(_table(name, by_table[name]) for name in sorted(by_table)),
    )


def timestamp(moment: datetime) -> str:
    """A time as the run's files write it: UTC, as in 2020-06-01T13:30:00Z."""
    return to_utc(moment).isoformat().replace("+00:00", "Z")


def row_line(record: AccessRecord) -> str:
    """One row as the hash sees it: the canonical JSON of its key's values, then its
    `available_at`, then its `source_ref`.

        ["abbvie","2019-04-30","2019-04-30T20:00:00Z","tiingo ABBV 2019-04-30"]
    """
    return _ROW.encode(
        [
            *(_plain(value) for value in record.key),
            timestamp(record.available_at),
            record.source_ref,
        ]
    )


def rows_hash(lines: Iterable[str]) -> str:
    """The SHA-256 of rows' lines (`row_line`), sorted and joined by newlines, in
    UTF-8."""
    return hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()


def _table(name: str, records: set[AccessRecord]) -> TableInputs:
    lines = {record: row_line(record) for record in records}
    groups: dict[GroupKey, list[AccessRecord]] = {}
    for record in records:
        key = _plain(record.key[0]) if record.key else None
        groups.setdefault(key, []).append(record)
    summaries = []
    for key, members in groups.items():
        # The newest row, and among rows that became known together, the last line.
        newest = max(members, key=lambda r: (r.available_at, lines[r]))
        summaries.append(
            InputGroup(key, len(members), newest.available_at, newest.source_ref)
        )
    known = [record.available_at for record in records]
    return TableInputs(
        table=name,
        rows=len(records),
        earliest_available_at=min(known),
        latest_available_at=max(known),
        sha256=rows_hash(lines.values()),
        groups=tuple(sorted(summaries, key=lambda group: _order(group.key))),
    )


def _order(key: GroupKey) -> tuple[str, str | int | float]:
    """Where a group sorts. A table's keys share a type; its name comes first so that
    the order is still defined if one ever doesn't."""
    return ("", 0) if key is None else (type(key).__name__, key)


def _plain(value: object) -> GroupKey:
    """A key's value as JSON writes it: a time in UTC, a date as 2020-06-01."""
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value + 0.0  # -0.0 becomes 0.0, as canonical JSON writes it
    if isinstance(value, datetime):
        return timestamp(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
