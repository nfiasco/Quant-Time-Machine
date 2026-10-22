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

SECURITIES = TableSpec(
    name="securities",
    key=("security_id",),
    columns={
        "security_id": "VARCHAR",
        "ticker": "VARCHAR",
        "name": "VARCHAR",
        "cik": "BIGINT",
        "share_class": "VARCHAR",
        "effective_date": "DATE",
    },
)
"""Each curated security's ticker, name, and CIK over time (S5.2).

A row is a change that took effect on `effective_date`, known from 00:00 ET that day, so
a security's latest version at a knowledge time is what applied then. `ticker` is None
once the security was delisted."""

SEC_TICKERS = TableSpec(
    name="sec_tickers",
    key=("cik", "ticker"),
    columns={"cik": "BIGINT", "ticker": "VARCHAR", "name": "VARCHAR"},
)
"""Snapshots of SEC's ticker file, which lists only the tickers in use when it's
downloaded (S5.2). Every row of a snapshot has that download's time as `available_at`,
flagged `time_assumed`."""

TABLES: dict[str, TableSpec] = {
    spec.name: spec for spec in (MACRO_OBSERVATIONS, SECURITIES, SEC_TICKERS)
}
