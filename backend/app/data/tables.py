"""Every table in the point-in-time store, by name.

Each ingestion task defines its table here (S4.2, S5.3, S6.2), so that every reader
sees the same list no matter which modules were imported first. For example:

    MACRO_OBSERVATIONS = TableSpec(
        name="macro_observations",
        key=("series_id", "observation_date"),
        columns={"series_id": "VARCHAR", "observation_date": "DATE", "value": "DOUBLE"},
    )
    TABLES = {spec.name: spec for spec in (MACRO_OBSERVATIONS,)}

`PointInTimeView` reads the tables listed in TABLES, and the test fixture loader
matches each tests/fixtures/<table>.csv to one of them.
"""

from app.data.store import TableSpec

TABLES: dict[str, TableSpec] = {}
