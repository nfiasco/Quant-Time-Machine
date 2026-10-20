"""Load the CSV files in tests/fixtures/ into a point-in-time store.

The files' format and rules are in tests/fixtures/README.md. Tests usually get a loaded
store from the `fixture_store` fixture in conftest.py instead of calling this directly.
"""

import csv
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

import pytest

from app.data.store import TableSpec, write_rows
from app.data.timeutil import to_utc

FIXTURES = Path(__file__).parent / "fixtures"

TEST_OBSERVATIONS = TableSpec(
    name="test_observations",
    key=("series_id", "period"),
    columns={"series_id": "VARCHAR", "period": "DATE", "value": "DOUBLE"},
)
"""A synthetic table for testing the store and the view, independent of real tables."""

TEST_TABLES = {TEST_OBSERVATIONS.name: TEST_OBSERVATIONS}

CANARY_YEAR = 2099


def _boolean(text: str) -> bool:
    if text.lower() not in ("true", "false"):
        raise ValueError(f"expected true or false, got {text!r}")
    return text.lower() == "true"


# How a CSV cell becomes a value of each column type. An empty cell is None.
_PARSERS: dict[str, Callable[[str], object]] = {
    "VARCHAR": str,
    "DATE": date.fromisoformat,
    # A timestamp without an offset is naive, and to_utc rejects it (rule 1).
    "TIMESTAMPTZ": lambda text: to_utc(datetime.fromisoformat(text)),
    "DOUBLE": float,
    "BIGINT": int,
    "BOOLEAN": _boolean,
}


def load_fixture(store: Path, spec: TableSpec, path: Path) -> None:
    """Load one fixture CSV into `store` through `write_rows`, as ingestion would."""
    with path.open(newline="", encoding="utf-8") as file:
        records = list(csv.DictReader(file))
    rows = []
    for record in records:
        row: dict[str, object] = {}
        for column, text in record.items():
            kind = spec.all_columns.get(column)
            if text == "":
                row[column] = None
            elif kind is None:
                row[column] = text  # an unknown column, which write_rows reports
            else:
                row[column] = _PARSERS[kind](text)
        rows.append(row)

    if not any(_is_canary(row) for row in rows):
        pytest.fail(
            f"{path.name} needs a canary row with available_at in {CANARY_YEAR}"
        )
    write_rows(store, spec, rows)


def _is_canary(row: dict[str, object]) -> bool:
    available_at = row.get("available_at")
    return isinstance(available_at, datetime) and available_at.year >= CANARY_YEAR
