"""Every table in the point-in-time store, by name.

Each ingestion task defines its table here (S4.2, S5.3, S6.2), so that every reader
sees the same list no matter which modules were imported first. `PointInTimeView` reads
the tables listed in TABLES, and the test fixture loader matches each
tests/fixtures/<table>.csv to one of them, so a new table needs a fixture file too.
"""

from app.data.store import TableSpec

MACRO_OBSERVATIONS = TableSpec(
    name="macro_observations",
    key=("series_id", "observation_date"),
    columns={
        "series_id": "VARCHAR",
        "observation_date": "DATE",
        "value": "DOUBLE",
        "vintage_date": "DATE",
    },
)
"""Every published version of each macro observation, from ALFRED (S4.2).

A version is the value from one vintage: `vintage_date` is ALFRED's `realtime_start`,
and `available_at` is that date at the release's time in New York (S4.3), or the end of
the day, flagged `time_assumed`, when the time isn't known. `value` is None when the
source published the observation as missing (FRED's ".")."""

TABLES: dict[str, TableSpec] = {spec.name: spec for spec in (MACRO_OBSERVATIONS,)}
