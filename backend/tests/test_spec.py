import copy
import json
import re
from datetime import time
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from app.backtest.spec import ExperimentSpec, SpecError, json_schema, parse_spec

REPOSITORY = Path(__file__).resolve().parents[2]
CANONICAL = Path(__file__).parent / "fixtures" / "specs" / "canonical.json"
SCHEMA_FILE = REPOSITORY / "doc" / "experiment-spec-v1.schema.json"
FRONTEND_TYPES = REPOSITORY / "frontend" / "features" / "backtests" / "types.ts"

DELETE = object()
"""Passed to `changed` to remove a field."""


@cache
def _canonical() -> dict[str, Any]:
    return json.loads(CANONICAL.read_text(encoding="utf-8"))


def canonical() -> dict[str, Any]:
    """The canonical spec (roadmap §3.4), as parsed JSON."""
    return copy.deepcopy(_canonical())


def changed(path: str, value: object) -> dict[str, Any]:
    """The canonical spec with the value at a dotted path set, or removed for DELETE."""
    spec = canonical()
    *parents, last = path.split(".")
    node: Any = spec
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    if value is DELETE:
        del node[last]
    elif isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return spec


def problems(spec: str | dict[str, Any]) -> list[tuple[str, str]]:
    """The fields and messages of an invalid spec's problems."""
    with pytest.raises(SpecError) as raised:
        parse_spec(spec)
    return [(problem.field, problem.message) for problem in raised.value.problems]


def test_the_canonical_fixture_is_the_roadmaps_example() -> None:
    roadmap = (REPOSITORY / "doc" / "roadmap.md").read_text(encoding="utf-8")
    section = roadmap.split("\n### 3.4 ", 1)[1].split("\n### ", 1)[0]
    (example,) = re.findall(r"```json\n(.*?)\n```", section, re.DOTALL)

    assert json.loads(example) == canonical()


def test_the_canonical_spec_is_valid() -> None:
    spec = parse_spec(CANONICAL.read_text(encoding="utf-8"))

    assert spec == parse_spec(canonical())  # JSON text or parsed JSON
    assert spec.schedule.decision_time == time(9, 30)
    assert spec.signals["mom_12_1"].type == "momentum"
    # Nothing is added or lost on the way back to JSON.
    assert spec.model_dump(mode="json") == canonical()


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("schedule.fill", "next_day_open"),
        ("schedule.decision", "first_trading_day 15:59 America/New_York"),
        ("portfolio.weighting", "value"),
        ("portfolio.long_only", False),
        ("filters", []),
        ("signals.mom_12_1.skip_months", 0),
        ("costs.bps_per_trade", 2.5),
        ("benchmark", "BRK.B"),
    ],
)
def test_other_valid_specs(path: str, value: object) -> None:
    assert isinstance(parse_spec(changed(path, value)), ExperimentSpec)


def test_a_1600_decision_fills_at_the_next_open() -> None:
    spec = changed("schedule.decision", "first_trading_day 16:00 America/New_York")
    spec["schedule"]["fill"] = "next_day_open"

    assert parse_spec(spec).schedule.decision_time == time(16)


INVALID = [
    ("costs", DELETE, "costs", "costs is required."),
    ("notes", "x", "notes", "notes isn't part of experiment spec version 1."),
    ("spec_version", 2, "spec_version", "spec_version must be 1."),
    ("name", "  ", "name", "name can't be blank."),
    (
        "universe.id",
        "sp500",
        "universe.id",
        "universe.id must be 'starter_large_caps'.",
    ),
    ("universe", "starter_large_caps", "universe", "universe must be an object."),
    (
        "period.start",
        "2010-13-01",
        "period.start",
        "period.start must be a date such as 2020-04-01.",
    ),
    (
        "period.end",
        "2009-12-31",
        "period.end",
        "period.end must be after period.start, 2010-01-01.",
    ),
    (
        "schedule.decision",
        "first_trading_day 9:30",
        "schedule.decision",
        (
            "schedule.decision must look like 'first_trading_day 09:30 "
            "America/New_York': the first trading day of each month, at a New York "
            "time."
        ),
    ),
    (
        "schedule.decision",
        "first_trading_day 16:00 America/New_York",
        "schedule.decision",
        (
            "schedule.decision must be before the 16:00 close for a same_day_close "
            "fill, because a fill comes strictly after its decision. Decide earlier, "
            "or use next_day_open."
        ),
    ),
    (
        "schedule.fill",
        "next_close",
        "schedule.fill",
        "schedule.fill must be 'same_day_close' or 'next_day_open'.",
    ),
    (
        "signals.mom_12_1.type",
        "momentun",
        "signals.mom_12_1.type",
        ("signals.mom_12_1.type must be 'revenue_growth_acceleration' or 'momentum'."),
    ),
    (
        "signals.mom_12_1.type",
        DELETE,
        "signals.mom_12_1.type",
        "signals.mom_12_1.type is required.",
    ),
    (
        "signals.mom_12_1.lookback_months",
        0,
        "signals.mom_12_1.lookback_months",
        "signals.mom_12_1.lookback_months must be at least 1.",
    ),
    (
        "signals.mom_12_1.lookback_months",
        12.5,
        "signals.mom_12_1.lookback_months",
        "signals.mom_12_1.lookback_months must be a whole number.",
    ),
    (
        "signals.mom_12_1.skip_months",
        12,
        "signals.mom_12_1.skip_months",
        "signals.mom_12_1.skip_months must be less than lookback_months, 12.",
    ),
    (
        "signals.rev_accel.basis",
        "qoq",
        "signals.rev_accel.basis",
        "signals.rev_accel.basis must be 'yoy_quarterly'.",
    ),
    (
        "signals.Mom-12",
        {"type": "momentum", "lookback_months": 12, "skip_months": 1},
        "signals.Mom-12",
        (
            "signals.Mom-12 isn't a valid signal ID: use lowercase letters, digits, "
            "and underscores, starting with a letter."
        ),
    ),
    (
        "filters.1.signal",
        "mom_12",
        "filters.1.signal",
        ("filters.1.signal must name a signal in signals: 'rev_accel' or 'mom_12_1'."),
    ),
    (
        "filters.0.op",
        "!=",
        "filters.0.op",
        "filters.0.op must be '>', '>=', '<' or '<='.",
    ),
    (
        "filters.0.value",
        "big",
        "filters.0.value",
        "filters.0.value must be a number.",
    ),
    (
        "filters.0.value",
        float("inf"),
        "filters.0.value",
        "filters.0.value must be a finite number.",
    ),
    ("filters", {}, "filters", "filters must be a list."),
    (
        "portfolio.weighting",
        "market_cap",
        "portfolio.weighting",
        "portfolio.weighting must be 'equal' or 'value'.",
    ),
    (
        "portfolio.long_only",
        "maybe",
        "portfolio.long_only",
        "portfolio.long_only must be true or false.",
    ),
    (
        "benchmark",
        "spy",
        "benchmark",
        "benchmark must be a ticker in capitals, such as SPY.",
    ),
    (
        "costs.bps_per_trade",
        -1,
        "costs.bps_per_trade",
        "costs.bps_per_trade must be at least 0.",
    ),
]
"""A change to the canonical spec, and the one problem it should report."""


@pytest.mark.parametrize(
    ("path", "value", "field", "message"),
    INVALID,
    ids=[
        f"{path}={'deleted' if value is DELETE else value}"
        for path, value, *_ in INVALID
    ],
)
def test_errors_name_their_field(
    path: str, value: object, field: str, message: str
) -> None:
    assert problems(changed(path, value)) == [(field, message)]


def test_filters_need_a_signal_to_name() -> None:
    assert problems(changed("signals", {})) == [
        (
            "filters.0.signal",
            "filters.0.signal must name a signal in signals, which has none.",
        )
    ]


def test_every_problem_is_reported() -> None:
    spec = changed("schedule.fill", "next_close")
    del spec["costs"]

    with pytest.raises(SpecError) as raised:
        parse_spec(spec)

    assert [problem.field for problem in raised.value.problems] == [
        "schedule.fill",
        "costs",
    ]
    assert str(raised.value) == (
        "schedule.fill must be 'same_day_close' or 'next_day_open'. costs is required."
    )


def test_text_that_isnt_json() -> None:
    ((field, message),) = problems('{"spec_version": 1,')

    assert field == "spec"
    assert message.startswith("The spec isn't valid JSON: EOF while parsing")


def test_the_committed_schema_is_current() -> None:
    assert SCHEMA_FILE.read_text(encoding="utf-8") == (
        json.dumps(json_schema(), indent=2) + "\n"
    ), (
        "doc/experiment-spec-v1.schema.json is out of date. From backend/, run "
        "uv run python -m app.backtest.spec > ../doc/experiment-spec-v1.schema.json"
    )


def test_the_spec_matches_the_frontend_types() -> None:
    # The web app's ExperimentSpec type and these models must use the same field names
    # and the same string values. Change both together.
    code = re.sub(
        r"/\*.*?\*/|//[^\n]*",
        "",
        FRONTEND_TYPES.read_text(encoding="utf-8"),
        flags=re.DOTALL,
    )
    fields: set[str] = set()
    values: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            fields.update(node.get("properties", {}))
            values.update(
                value
                for value in [node.get("const"), *node.get("enum", [])]
                if isinstance(value, str)
            )
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(json_schema())

    assert set(re.findall(r"(\w+)\??:", code)) == fields
    assert set(re.findall(r'"([^"]*)"', code)) == values
