"""Revenue growth and its acceleration, from the quarters filed by the decision (S7.4;
doc/reference/signals.md, sections 2 and 3).

Both read a company's quarterly revenue as known at the decision: each quarter's latest
value filed by then in a 10-Q or a 10-K, and a quarter no filing reported, such as a
fourth quarter, derived from two year-to-date totals
(`PointInTimeView.get_fundamentals_as_of`; doc/reference/time-model.md, rule 6). With q
the latest quarter known and R(q) its revenue:

    revenue_growth               g(q) = R(q) / R(q − 4) − 1
    revenue_growth_acceleration  a(q) = g(q) − g(q − 1)

q − 4 is the same quarter a year earlier: the one that ended 350 to 380 days before q
did, so 52- and 53-week years count. q − 1 is the quarter before q: it ended 80 to 119
days before, as PepsiCo's 16-week fourth quarter does. Both values are fractions: a
growth of 0.05 is 5%, and an acceleration of 0.02 is 2 percentage points.

Minimum history: q and q − 4 for growth, and q, q − 1, q − 4, and q − 5 for
acceleration, each with a positive revenue. q must also be recent: one that ended more
than `MAX_QUARTER_AGE_DAYS` before the decision gives no value, with the reason.
"""

from collections.abc import Callable, Sequence
from datetime import date

from app.backtest.signals.base import SignalValue, decision_day
from app.backtest.spec import RevenueGrowthAccelerationSignal, RevenueGrowthSignal
from app.data.fundamentals import quarters_spanned
from app.data.records import Fundamental, UniverseMember
from app.data.view import PointInTimeView

MAX_QUARTER_AGE_DAYS = 200
"""The oldest the latest quarter known can be, in days from its end to the decision. A
company that files on time reports a later quarter first. Its slowest report, the 10-K,
is due 60 to 90 days after its year ends, or 105 with an extension, so at a monthly
decision its latest quarter is at most about 186 days old. An older one means a later
quarter is missing from what we read: its filing, or a revenue tag the metric doesn't
list (app/data/sources/metrics.toml)."""

QUARTERS_READ = 8
"""How many of the latest quarters known to read: q − 5 is among them even when a
quarter or two are missing."""


class _NoValue(Exception):
    """Why a member has no value, as a sentence a results page can show."""


def revenue_growth(
    view: PointInTimeView,
    members: Sequence[UniverseMember],
    params: RevenueGrowthSignal,
) -> dict[str, SignalValue]:
    """Each member's year-over-year revenue growth in its latest quarter known, by
    security ID."""
    return _each(view, members, _growth)


def revenue_growth_acceleration(
    view: PointInTimeView,
    members: Sequence[UniverseMember],
    params: RevenueGrowthAccelerationSignal,
) -> dict[str, SignalValue]:
    """Each member's revenue growth in its latest quarter known minus its growth in the
    quarter before, by security ID."""
    return _each(view, members, _acceleration)


def _each(
    view: PointInTimeView,
    members: Sequence[UniverseMember],
    compute: Callable[[Sequence[Fundamental], Fundamental], float],
) -> dict[str, SignalValue]:
    """`compute` for each member's latest quarter known, or the reason it can't be."""
    day = decision_day(view)
    found = {}
    for member in members:
        try:
            quarters = _quarters(view, member, day)
            found[member.security_id] = SignalValue(compute(quarters, quarters[-1]))
        except _NoValue as reason:
            found[member.security_id] = SignalValue(None, str(reason))
    return found


def _quarters(
    view: PointInTimeView, member: UniverseMember, day: date
) -> list[Fundamental]:
    """A member's latest quarters of revenue known, oldest first. The last one ended at
    most `MAX_QUARTER_AGE_DAYS` before `day`."""
    if member.ticker is None:  # the engine leaves such members out
        raise _NoValue("It had stopped trading by then.")
    quarters = view.get_fundamentals_as_of(member.ticker, "revenue", QUARTERS_READ)
    if not quarters:
        raise _NoValue("No quarterly revenue was known then.")
    latest = quarters[-1].period_end
    age = (day - latest).days
    if age > MAX_QUARTER_AGE_DAYS:
        raise _NoValue(
            f"Its latest quarter known ended on {latest}, {age} days before: more "
            f"than {MAX_QUARTER_AGE_DAYS}, so later quarters are missing."
        )
    return quarters


def _growth(quarters: Sequence[Fundamental], quarter: Fundamental) -> float:
    """g(q): a quarter's revenue over the same quarter's a year earlier, minus 1."""
    earlier = _before(quarters, quarter, 4)
    for each in (quarter, earlier):
        if each.value <= 0:
            raise _NoValue(
                f"Revenue for the quarter that ended on {each.period_end} wasn't "
                "positive, so growth isn't defined."
            )
    return quarter.value / earlier.value - 1


def _acceleration(quarters: Sequence[Fundamental], quarter: Fundamental) -> float:
    """a(q) = g(q) − g(q − 1)."""
    growth = _growth(quarters, quarter)
    return growth - _growth(quarters, _before(quarters, quarter, 1))


def _before(
    quarters: Sequence[Fundamental], quarter: Fundamental, n: int
) -> Fundamental:
    """The quarter `n` quarters before `quarter`, by how long before it that quarter
    ended: 4 for the same quarter a year earlier, 1 for the quarter before."""
    for earlier in reversed(quarters):
        if quarters_spanned((quarter.period_end - earlier.period_end).days) == n:
            return earlier
    which = "a year before" if n == 4 else "before"
    raise _NoValue(
        f"Revenue for the quarter {which} the one that ended on {quarter.period_end} "
        "wasn't known."
    )
