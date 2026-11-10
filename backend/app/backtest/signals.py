"""What the simulation loop asks of a signal (S7.3).

A spec names each of its signals' kind by its `type` (app/backtest/spec.py), and at
every decision the engine evaluates each signal for the universe's members, through
the view bound to the decision's time, so a signal can read only what was known then
(app/backtest/simulation.py).

- `Signal` is what a kind of signal implements.
- `SignalValue` is its answer for one security: a value, or why there's none.
- `SIGNALS` lists the kinds the engine can evaluate, by `type`.

The library itself is S7.4's: momentum, revenue growth and its acceleration, and macro
conditions. Until it adds them to `SIGNALS`, the engine rejects a spec that uses one,
and tests pass signals of their own.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from app.data.records import UniverseMember
from app.data.view import PointInTimeView


@dataclass(frozen=True)
class SignalValue:
    """A signal's value for one security at one decision, or why it has none."""

    value: float | None
    reason: str | None = None
    """Why there's no value, as a sentence a results page can show: "Fewer than 13
    months of prices were known." None when there's a value."""

    def __post_init__(self) -> None:
        if (self.value is None) == (self.reason is None):
            raise ValueError("a signal value has either a value or a reason, not both")
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError(f"a signal's value must be finite, not {self.value}")


class Signal(Protocol):
    """One kind of signal, evaluated for a universe's members at a decision."""

    def __call__(
        self,
        view: PointInTimeView,
        members: Sequence[UniverseMember],
        params: Any,
    ) -> Mapping[str, SignalValue]:
        """Each member's value as known at the view's knowledge time, by security ID.

        Every member gets a value, or a reason it has none. `params` is the signal's
        object in the spec, such as a `MomentumSignal`. The members all trade then: the
        engine leaves out those that had stopped trading. Read only through `view`.
        """
        ...


SIGNALS: Mapping[str, Signal] = MappingProxyType({})
"""The kinds of signal the engine can evaluate, by their `type` in a spec. S7.4 adds
momentum and revenue growth acceleration."""
