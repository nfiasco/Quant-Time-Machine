"""Experiment spec version 1: the validated JSON document that describes a backtest (S7.1).

Every backtest is one of these, whether it's built in the web form or, later, by the
assistant (roadmap §3.4). The models match the frontend's `ExperimentSpec` type in
frontend/features/backtests/types.ts, field for field, and tests/test_spec.py keeps the
two in sync.

- `parse_spec` validates a spec, given as JSON or as parsed JSON. It raises `SpecError`,
  which names each invalid field the way the API's 422 errors do: "schedule.fill must
  be 'same_day_close' or 'next_day_open'."
- `json_schema()` is the spec's JSON Schema, for the API and the assistant. It's
  committed as doc/experiment-spec-v1.schema.json, and printed by

      uv run python -m app.backtest.spec

- `signal_types()` lists the kinds of signal a spec can use, each with its own JSON
  Schema, for the catalog (S8.5).

A spec checks only what it can on its own: shapes, names, and the rules between its
fields. Whether our data covers it, such as fundamentals before XBRL, or whether the
engine supports an option, such as value weights, is for the engine to say (S7.3).
"""

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time
from typing import Annotated, Any, Literal, Self, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import ErrorDetails, PydanticCustomError

from app.data.sources.universes import UNIVERSES

FillRule = Literal["same_day_close", "next_day_open"]
"""When a decision's trades fill (doc/time-model.md, rule 10)."""

DECISION = re.compile(
    r"first_trading_day ([01][0-9]|2[0-3]):([0-5][0-9]) America/New_York"
)
"""How a spec writes its decision time: "first_trading_day 09:30 America/New_York".
No named groups, so that the pattern is valid in JSON Schema too."""

REGULAR_CLOSE = time(16)
"""The NYSE's close on a regular day, New York time. A same-day close fill needs a
decision before it."""

SIGNAL_ID = re.compile(r"[a-z][a-z0-9_]*")
TICKER = re.compile(r"[A-Z0-9][A-Z0-9.-]*")

_SIGNAL_TYPES = {"revenue_growth_acceleration", "momentum"}
"""The `type` of each kind of signal. Pydantic puts it in the location of an error
inside a signal, after the signal's ID."""


def _broken(field: str, rule: str) -> PydanticCustomError:
    """An error for `field`, a dotted path inside the value being validated ("" for the
    value itself), which breaks `rule`: what follows the field's name in the message,
    such as "must be after period.start"."""
    return PydanticCustomError(
        "spec_rule", "{field} {rule}", {"field": field, "rule": rule}
    )


def _one_of(values: Iterable[str]) -> str:
    """Quoted values joined as pydantic lists a literal's: "'a', 'b' or 'c'"."""
    quoted = [f"'{value}'" for value in values]
    if len(quoted) == 1:
        return quoted[0]
    return f"{', '.join(quoted[:-1])} or {quoted[-1]}"


class _Part(BaseModel):
    """A part of a spec: it takes no fields but its own, and never changes."""

    model_config = ConfigDict(
        extra="forbid", frozen=True, use_attribute_docstrings=True
    )


class UniverseSpec(_Part):
    """Which securities are eligible at each decision."""

    type: Literal["point_in_time_list"]
    """A curated list whose members change on their effective dates."""
    id: str
    """The list, such as "starter_large_caps"."""

    @field_validator("id")
    @classmethod
    def _known(cls, universe: str) -> str:
        if universe not in UNIVERSES.by_name:
            raise _broken("", f"must be {_one_of(UNIVERSES.by_name)}")
        return universe


class PeriodSpec(_Part):
    """The dates the backtest covers, both included."""

    start: date
    end: date
    """After `start`."""

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        if self.end <= self.start:
            raise _broken("end", f"must be after period.start, {self.start}")
        return self


class ScheduleSpec(_Part):
    """When decisions are made, and when their trades fill."""

    rebalance: Literal["monthly"]
    decision: str = Field(json_schema_extra={"pattern": f"^{DECISION.pattern}$"})
    """The first trading day of each month at a New York time, such as the default,
    "first_trading_day 09:30 America/New_York"."""
    fill: FillRule
    """"same_day_close", the default, fills at the decision day's close, and
    "next_day_open" at the next session's open. Either comes strictly after the
    decision."""

    @field_validator("decision")
    @classmethod
    def _decision_format(cls, decision: str) -> str:
        if DECISION.fullmatch(decision) is None:
            raise _broken(
                "",
                "must look like 'first_trading_day 09:30 America/New_York': the first "
                "trading day of each month, at a New York time",
            )
        return decision

    @model_validator(mode="after")
    def _fill_after_decision(self) -> Self:
        if self.fill == "same_day_close" and self.decision_time >= REGULAR_CLOSE:
            raise _broken(
                "decision",
                "must be before the 16:00 close for a same_day_close fill, because a "
                "fill comes strictly after its decision. Decide earlier, or use "
                "next_day_open",
            )
        return self

    @property
    def decision_time(self) -> time:
        """The decisions' New York time of day, such as 09:30."""
        match = DECISION.fullmatch(self.decision)
        assert match is not None  # checked when the spec was made
        return time(int(match[1]), int(match[2]))


class RevenueGrowthAccelerationSignal(_Part):
    """This quarter's year-over-year revenue growth minus last quarter's."""

    type: Literal["revenue_growth_acceleration"]
    basis: Literal["yoy_quarterly"]
    """Each quarter's growth over the same quarter a year earlier."""


class MomentumSignal(_Part):
    """The total return over a lookback, leaving out the most recent months."""

    type: Literal["momentum"]
    lookback_months: int = Field(ge=1)
    """How many months back the return starts: 12 for 12-1 momentum."""
    skip_months: int = Field(ge=0)
    """How many of the latest months to leave out: 1 for 12-1 momentum. Fewer than
    `lookback_months`."""

    @model_validator(mode="after")
    def _skip_within_lookback(self) -> Self:
        if self.skip_months >= self.lookback_months:
            raise _broken(
                "skip_months",
                f"must be less than lookback_months, {self.lookback_months}",
            )
        return self


SignalSpec = Annotated[
    RevenueGrowthAccelerationSignal | MomentumSignal, Field(discriminator="type")
]
"""A signal from the library (S7.4), chosen by its `type`."""


class FilterSpec(_Part):
    """A condition every holding must meet at a decision, such as rev_accel > 0."""

    signal: str
    """The ID of a signal in `signals`."""
    op: Literal[">", ">=", "<", "<="]
    value: float = Field(allow_inf_nan=False)


class PortfolioSpec(_Part):
    """How the securities that pass the filters are weighted."""

    weighting: Literal["equal", "value"]
    """"value" weights by market cap."""
    long_only: bool


class CostsSpec(_Part):
    """What trading costs."""

    bps_per_trade: float = Field(ge=0, allow_inf_nan=False)
    """Basis points of the value traded, charged on every trade: 10 is 0.1%."""


class ExperimentSpec(_Part):
    """Experiment spec version 1: everything that defines a backtest."""

    spec_version: Literal[1]
    name: str
    """What the experiment tests, in a few words."""
    universe: UniverseSpec
    period: PeriodSpec
    schedule: ScheduleSpec
    signals: dict[str, SignalSpec] = Field(
        json_schema_extra={"propertyNames": {"pattern": f"^{SIGNAL_ID.pattern}$"}}
    )
    """The signals the filters use, each under an ID of lowercase letters, digits, and
    underscores, such as "mom_12_1"."""
    filters: list[FilterSpec]
    """Conditions every holding must meet, all of them."""
    portfolio: PortfolioSpec
    benchmark: str = Field(json_schema_extra={"pattern": f"^{TICKER.pattern}$"})
    """The ticker the results are compared with, such as "SPY"."""
    costs: CostsSpec

    @field_validator("name")
    @classmethod
    def _not_blank(cls, name: str) -> str:
        if not name.strip():
            raise _broken("", "can't be blank")
        return name

    @field_validator("signals")
    @classmethod
    def _signal_ids(cls, signals: dict[str, SignalSpec]) -> dict[str, SignalSpec]:
        for signal_id in signals:
            if SIGNAL_ID.fullmatch(signal_id) is None:
                raise _broken(
                    signal_id,
                    "isn't a valid signal ID: use lowercase letters, digits, and "
                    "underscores, starting with a letter",
                )
        return signals

    @field_validator("filters")
    @classmethod
    def _filters_name_signals(
        cls, filters: list[FilterSpec], info: ValidationInfo
    ) -> list[FilterSpec]:
        signals = info.data.get("signals")
        if signals is None:  # invalid itself, and reported already
            return filters
        for index, condition in enumerate(filters):
            if condition.signal not in signals:
                raise _broken(
                    f"{index}.signal",
                    f"must name a signal in signals: {_one_of(signals)}"
                    if signals
                    else "must name a signal in signals, which has none",
                )
        return filters

    @field_validator("benchmark")
    @classmethod
    def _ticker(cls, benchmark: str) -> str:
        if TICKER.fullmatch(benchmark) is None:
            raise _broken("", "must be a ticker in capitals, such as SPY")
        return benchmark


@dataclass(frozen=True)
class SpecProblem:
    """One invalid field of a spec."""

    field: str
    """Its dotted path, as the API's errors write it: "schedule.fill", or
    "filters.1.signal" for the second filter's signal."""
    message: str
    """A sentence that starts with the field: "costs is required.\""""


class SpecError(ValueError):
    """A spec that isn't valid. Its message joins its problems' sentences."""

    def __init__(self, problems: Sequence[SpecProblem]) -> None:
        super().__init__(" ".join(problem.message for problem in problems))
        self.problems = tuple(problems)


def parse_spec(spec: str | bytes | Mapping[str, Any]) -> ExperimentSpec:
    """Validate an experiment spec, given as JSON or as parsed JSON.

    Raises SpecError, which names each invalid field.
    """
    try:
        if isinstance(spec, str | bytes):
            return ExperimentSpec.model_validate_json(spec)
        return ExperimentSpec.model_validate(spec)
    except ValidationError as error:
        raise SpecError([_problem(item) for item in error.errors()]) from None


def json_schema() -> dict[str, Any]:
    """The JSON Schema of experiment spec version 1."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **ExperimentSpec.model_json_schema(),
    }


@dataclass(frozen=True)
class SignalType:
    """A kind of signal a spec can use (S8.5)."""

    type: str
    """As a spec writes it, such as "momentum"."""
    description: str
    schema: dict[str, Any]
    """The JSON Schema of its object in a spec's `signals`, `type` included: the
    schema `json_schema()` lists under $defs."""


def signal_types() -> list[SignalType]:
    """Each kind of signal in the library, in the order `SignalSpec` lists them. A
    signal added to `SignalSpec` (S7.4) is listed with no other change."""
    (union, _) = get_args(SignalSpec)
    found = []
    for model in get_args(union):
        schema = model.model_json_schema()
        (kind,) = get_args(model.model_fields["type"].annotation)
        found.append(SignalType(kind, schema["description"], schema))
    return found


def _problem(error: ErrorDetails) -> SpecProblem:
    """One of pydantic's errors as a field and a sentence."""
    location = [str(part) for part in error["loc"]]
    if len(location) > 2 and location[0] == "signals" and location[2] in _SIGNAL_TYPES:
        del location[2]  # the signal's type, after its ID
    kind, context = error["type"], error.get("ctx") or {}
    if kind == "spec_rule" and context["field"]:
        location.append(context["field"])
    elif kind in ("union_tag_invalid", "union_tag_not_found"):
        location.append("type")
    field = ".".join(location) or "spec"
    return SpecProblem(field, _explain(field, kind, context, error["msg"]))


def _explain(field: str, kind: str, context: Mapping[str, Any], message: str) -> str:
    match kind:
        case "spec_rule":
            return f"{field} {context['rule']}."
        case "missing" | "union_tag_not_found":
            return f"{field} is required."
        case "extra_forbidden":
            return f"{field} isn't part of experiment spec version 1."
        case "literal_error":
            return f"{field} must be {context['expected']}."
        case "union_tag_invalid":
            tags = [tag.strip("'") for tag in context["expected_tags"].split(", ")]
            return f"{field} must be {_one_of(tags)}."
        case "greater_than_equal":
            bound = context["ge"]  # 0.0 for a float field
            if isinstance(bound, float) and bound.is_integer():
                bound = int(bound)
            return f"{field} must be at least {bound}."
        case "int_parsing" | "int_from_float" | "int_type":
            return f"{field} must be a whole number."
        case "float_parsing" | "float_type":
            return f"{field} must be a number."
        case "finite_number":
            return f"{field} must be a finite number."
        case "bool_parsing" | "bool_type":
            return f"{field} must be true or false."
        case "string_type":
            return f"{field} must be a string."
        case "dict_type" | "model_type" | "model_attributes_type":
            return f"{field} must be an object."
        case "list_type":
            return f"{field} must be a list."
        case "json_invalid":
            return f"The spec isn't valid JSON: {context['error']}."
    if kind.startswith("date"):
        return f"{field} must be a date such as 2020-04-01."
    return f"{field} is invalid: {message.rstrip('.')}."


if __name__ == "__main__":
    print(json.dumps(json_schema(), indent=2))
