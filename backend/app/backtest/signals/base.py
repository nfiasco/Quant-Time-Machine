"""What the simulation loop asks of a signal (S7.3), and what the library's signals share
(S7.4).

A spec names each of its signals' kind by its `type` (app/backtest/spec.py), and at
every decision the engine evaluates each signal for the universe's members, through
the view bound to the decision's time, so a signal can read only what was known then
(app/backtest/simulation.py).

- `Signal` is what a kind of signal implements.
- `SignalValue` is its answer for one security: a value, or why there's none.
- `decision_day` and `months_before` place a signal's inputs on the calendar.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from app.data.records import UniverseMember
from app.data.timeutil import ET
from app.data.view import PointInTimeView


@dataclass(frozen=True)
class SignalValue:
    """A signal's value for one security at one decision, or why it has none."""

    value: float | None
    reason: str | None = None
    """Why there's no value, as a sentence a results page can show: "It had no close on
    2019-12-31, the start of its 12-1 momentum window." None when there's a value."""

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


def decision_day(view: PointInTimeView) -> date:
    """The New York date of the view's knowledge time: the day of the decision it
    serves."""
    return view.knowledge_time.astimezone(ET).date()


def months_before(month: date, months: int) -> date:
    """The first day of the month `months` before `month`'s: 2019-06-01 is 12 months
    before June 2020, and `month` itself, as its first day, is 0 months before."""
    index = month.year * 12 + month.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)
