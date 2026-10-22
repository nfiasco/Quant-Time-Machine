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
