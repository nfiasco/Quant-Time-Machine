"""What point-in-time reads return: one frozen dataclass per kind of record.

Field names match the API contract (doc/api-v1.md), so the /v1 endpoints (S8.2) can
return records as they are. Every record carries its provenance: when it became public
(`available_at`, in UTC), whether that time was assumed rather than published
(`time_assumed`, doc/time-model.md rule 11), and where it came from (`source` and
`source_ref`).
"""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class MacroObservation:
    """One observation of a macro series, as published by the knowledge time (S4.4)."""

    series_id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str
    release: str
    """The release it comes out in, such as "Employment Situation"."""
    period: date
    """The observation date: 2020-05-01 is May 2020."""
    value: float | None
    """None when the source published the observation as missing."""
    vintage_date: date
    """When this version was published (ALFRED's `realtime_start`)."""
    available_at: datetime
    time_assumed: bool
    source: str
    source_ref: str


@dataclass(frozen=True)
class PriceBar:
    """One raw daily bar, as known at the knowledge time (S6.3).

    Prices are as traded, never adjusted for later splits or dividends.
    """

    security_id: str
    ticker: str
    """The ticker at the knowledge time: FB for Facebook's bars in 2020."""
    cik: int | None
    session_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    available_at: datetime
    """The session's close."""
    time_assumed: bool
    source: str
    source_ref: str


@dataclass(frozen=True)
class Security:
    """A security as identified at the knowledge time (S5.2)."""

    security_id: str
    """Ours, and stable: it doesn't change when the ticker, name, or CIK does."""
    ticker: str
    name: str
    """The name at the knowledge time, such as "Facebook, Inc." in 2020."""
    cik: int | None
    """SEC's ID for the company at the knowledge time, if it has one."""
    share_class: str | None
    effective_date: date | None
    """When this ticker, name, and CIK took effect; None if only SEC's file knows it."""
    available_at: datetime
    time_assumed: bool
    source: str
    source_ref: str
