"""ALFRED: every published version of the starter macro series (S4.2).

`uv run python -m app.data.ingest fred` loads each series in alfred_series.toml, in the
order listed (UNRATE first), into the `macro_observations` table:

1. `series/release` and `series`: FRED's metadata is checked against the config. A
   different release stops the run, and other differences are logged.
2. `series/observations` over the whole real-time range, 1776-07-04 to 9999-12-31.
   FRED's defaults are today's date, which returns today's revised values instead of
   every version (doc/time-model.md, "API defaults that mean today").

FRED answers with one record per real-time period: an observation's value from
`realtime_start` through `realtime_end`. Each becomes a row whose `vintage_date` is
`realtime_start`. The end date isn't stored: the next version's row supersedes the
value, and a stored end date would change when a new vintage arrives, which an
append-only store can't do. A missing value (FRED's ".") is stored as None.

Until release times are modeled (S4.3), every vintage becomes known at the end of its
date in New York and is flagged `time_assumed`, the conservative default
(doc/time-model.md, rules 7 and 11).
"""

import logging
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from app.data.http import SourceClient
from app.data.sources import IngestContext, IngestError
from app.data.store import write_rows
from app.data.tables import MACRO_OBSERVATIONS
from app.data.timeutil import market_time

logger = logging.getLogger(__name__)

CATALOG = Path(__file__).with_name("alfred_series.toml")

ALL_VINTAGES = {"realtime_start": "1776-07-04", "realtime_end": "9999-12-31"}
"""ALFRED's whole real-time range, so FRED returns every version, not today's."""

PAGE_SIZE = 100_000
"""The most observations FRED returns per request."""

END_OF_DAY = time(23, 59, 59, 999999)
"""When a vintage without a known release time becomes known (rule 7)."""


@dataclass(frozen=True)
class Release:
    """A FRED release: the publication a series comes out in."""

    key: str
    name: str
    fred_release_id: int


@dataclass(frozen=True)
class Series:
    """A series in the catalog, with FRED's descriptive metadata."""

    id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str
    release: Release


def load_catalog(path: Path = CATALOG) -> dict[str, Series]:
    """The series in a catalog file, by ID, in the file's order."""
    with path.open("rb") as file:
        config = tomllib.load(file)
    releases = {
        key: Release(key, entry["name"], entry["fred_release_id"])
        for key, entry in config["releases"].items()
    }
    catalog: dict[str, Series] = {}
    for entry in config["series"]:
        if entry["id"] in catalog:
            raise ValueError(f"{path.name}: {entry['id']} is listed twice")
        if entry["release"] not in releases:
            raise ValueError(
                f"{path.name}: {entry['id']} names an unknown release "
                f"{entry['release']!r}"
            )
        catalog[entry["id"]] = Series(
            id=entry["id"],
            title=entry["title"],
            units=entry["units"],
            frequency=entry["frequency"],
            seasonal_adjustment=entry["seasonal_adjustment"],
            release=releases[entry["release"]],
        )
    return catalog


SERIES = load_catalog()
"""The macro series catalog: every series ingestion loads and reads can ask for."""


def ingest(context: IngestContext) -> None:
    """Load every version of each series in the catalog, skipping stored ones."""
    for series in SERIES.values():
        check_metadata(context.client, series)
        rows = vintage_rows(series, fetch_observations(context.client, series.id))
        result = write_rows(context.store, MACRO_OBSERVATIONS, rows)
        logger.info(
            "%s: %d versions, %d new, %d already stored, %d conflicts",
            series.id,
            len(rows),
            result.written,
            result.skipped,
            result.conflicts,
        )


def check_metadata(client: SourceClient, series: Series) -> None:
    """Compare FRED's metadata for a series with the catalog's.

    A different release raises IngestError, because the release decides when each
    vintage became public. Other differences, such as a reworded title, are logged.
    """
    releases = client.get("series/release", {"series_id": series.id}).json()
    release = releases["releases"][0]
    if release["id"] != series.release.fred_release_id:
        raise IngestError(
            f"{series.id}: FRED says it comes from release {release['id']} "
            f"({release['name']}), but {CATALOG.name} says "
            f"{series.release.fred_release_id} ({series.release.name}). Fix the "
            "catalog first: the release decides when each vintage became public."
        )
    [info] = client.get("series", {"series_id": series.id}).json()["seriess"]
    for field in ("title", "units", "frequency", "seasonal_adjustment"):
        if info.get(field) != getattr(series, field):
            logger.warning(
                "%s: FRED's %s is %r, but %s says %r",
                series.id,
                field,
                info.get(field),
                CATALOG.name,
                getattr(series, field),
            )


def fetch_observations(client: SourceClient, series_id: str) -> list[dict[str, str]]:
    """Every version of every observation of a series, following FRED's pages."""
    observations: list[dict[str, str]] = []
    while True:
        page = client.get(
            "series/observations",
            {
                "series_id": series_id,
                **ALL_VINTAGES,
                "limit": PAGE_SIZE,
                "offset": len(observations),
            },
        ).json()
        observations += page["observations"]
        if not page["observations"] or len(observations) >= page["count"]:
            return observations


def vintage_rows(
    series: Series, observations: Iterable[Mapping[str, str]]
) -> list[dict[str, object]]:
    """One `macro_observations` row per version of each observation.

    Logs observations whose last version ends before 9999-12-31: a later vintage
    dropped them, and reads keep returning their last value.
    """
    rows: list[dict[str, object]] = []
    last: dict[str, Mapping[str, str]] = {}
    for record in observations:
        vintage = date.fromisoformat(record["realtime_start"])
        available_at, time_assumed = vintage_known_at(vintage)
        rows.append(
            {
                "series_id": series.id,
                "observation_date": date.fromisoformat(record["date"]),
                "value": None if record["value"] == "." else float(record["value"]),
                "vintage_date": vintage,
                "source": "alfred",
                "source_ref": f"{series.id} vintage {vintage.isoformat()}",
                "available_at": available_at,
                "time_assumed": time_assumed,
            }
        )
        latest = last.get(record["date"])
        if latest is None or record["realtime_start"] > latest["realtime_start"]:
            last[record["date"]] = record

    dropped = sorted(
        day
        for day, record in last.items()
        if record["realtime_end"] != ALL_VINTAGES["realtime_end"]
    )
    if dropped:
        logger.warning(
            "%s: %d observations are missing from the latest vintages, so reads "
            "return their last published value; for example %s",
            series.id,
            len(dropped),
            ", ".join(dropped[:3]),
        )
    return rows


def vintage_known_at(vintage: date) -> tuple[datetime, bool]:
    """When a vintage became public, and whether that time was assumed (rule 11).

    Release times arrive with S4.3. Until then, every vintage is known at the end of its
    date in New York, the latest time it could have been published that day.
    """
    return market_time(vintage, END_OF_DAY), True
