import hashlib
import json
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.data.errors import DataVersionError
from app.data.store import TableSpec, table_files, write_rows
from app.data.versions import (
    VERSIONS,
    latest_data_version,
    read_manifest,
    write_manifest,
)
from app.data.view import PointInTimeView
from tests.fixture_loader import TEST_OBSERVATIONS

OTHER = TableSpec(
    name="other_observations",
    key=("series_id", "period"),
    columns={"series_id": "VARCHAR", "period": "DATE", "value": "DOUBLE"},
)
TABLES = [TEST_OBSERVATIONS, OTHER]

T1 = datetime(2026, 11, 1, 14, 30, 5, 250000, tzinfo=UTC)
T2 = T1 + timedelta(hours=1)


def ingest(
    store: Path,
    spec: TableSpec,
    now: datetime,
    *values: tuple[date, float],
    source: str = "test",
) -> None:
    """Store made-up observations as an ingestion run at `now` would."""
    write_rows(
        store,
        spec,
        [
            {
                "series_id": "TEST",
                "period": period,
                "value": value,
                "source": source,
                "source_ref": f"synthetic: {period}",
                "available_at": datetime(2020, 7, 1, tzinfo=UTC),
                "time_assumed": False,
            }
            for period, value in values
        ],
        now=now,
    )


def values(
    store: Path, data_version: str | None, table: str = TEST_OBSERVATIONS.name
) -> list[float]:
    """Every value in `table` known on 2026-01-01, as `data_version` saw it."""
    with PointInTimeView(
        datetime(2026, 1, 1, tzinfo=UTC),
        data_version=data_version,
        store=store,
        tables=TABLES,
    ) as view:
        return [row["value"] for row in view._select(table)]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_manifest_lists_every_file_with_its_hash(store_dir: Path) -> None:
    ingest(
        store_dir,
        TEST_OBSERVATIONS,
        T1,
        (date(2020, 4, 1), 1.0),
        (date(2020, 5, 1), 2.0),
    )
    ingest(store_dir, OTHER, T1, (date(2020, 4, 1), 3.0), source="other")
    ingest(store_dir, TEST_OBSERVATIONS, T2, (date(2020, 6, 1), 4.0))

    manifest = write_manifest(store_dir, TABLES, now=T2, written_by="ingest test")

    assert manifest is not None
    assert manifest.data_version == "20261101T153005Z"
    path = store_dir / VERSIONS / "20261101T153005Z.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    assert content["written_by"] == "ingest test"
    assert content["ingested_through"] == "2026-11-01T15:30:05.250000Z"
    assert (content["rows"], content["sources"]) == (4, {"other": 1, "test": 3})
    table = content["tables"]["test_observations"]
    assert (table["rows"], table["sources"]) == (3, {"test": 3})
    files = table_files(store_dir, TEST_OBSERVATIONS)
    assert table["files"] == [
        {"name": f.name, "size": f.stat().st_size, "sha256": sha256(f)} for f in files
    ]
    assert read_manifest(store_dir, manifest.data_version) == manifest


def test_a_run_that_adds_nothing_keeps_the_newest_version(store_dir: Path) -> None:
    ingest(store_dir, TEST_OBSERVATIONS, T1, (date(2020, 4, 1), 1.0))
    first = write_manifest(store_dir, TABLES, now=T1)

    again = write_manifest(store_dir, TABLES, now=T2)

    assert first is not None
    assert again == first
    assert len(list((store_dir / VERSIONS).glob("*.json"))) == 1


def test_names_only_increase(store_dir: Path) -> None:
    # Versions cut in the same second, then one cut after the clock went back an hour.
    names = []
    for period, now in [
        (date(2020, 4, 1), T1),
        (date(2020, 5, 1), T1),
        (date(2020, 6, 1), T1 - timedelta(hours=1)),
    ]:
        ingest(store_dir, TEST_OBSERVATIONS, T1, (period, 1.0))
        manifest = write_manifest(store_dir, TABLES, now=now)
        assert manifest is not None
        names.append(manifest.data_version)

    assert names == ["20261101T143005Z", "20261101T143006Z", "20261101T143007Z"]
    assert latest_data_version(store_dir) == "20261101T143007Z"


def test_an_empty_store_has_no_data_version(store_dir: Path) -> None:
    assert write_manifest(store_dir, TABLES) is None
    assert latest_data_version(store_dir) is None
    assert not (store_dir / VERSIONS).exists()


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("20990101T000000Z", "There's no data version 20990101T000000Z"),
        ("../../etc/passwd", "isn't a data version"),
    ],
)
def test_an_unknown_data_version_is_refused(
    store_dir: Path, name: str, message: str
) -> None:
    with pytest.raises(DataVersionError, match=message):
        values(store_dir, name)


def test_a_pinned_view_fails_clearly_when_its_files_are_gone(store_dir: Path) -> None:
    ingest(store_dir, TEST_OBSERVATIONS, T1, (date(2020, 4, 1), 1.0))
    old = write_manifest(store_dir, TABLES, now=T1)
    # Rebuilding a table as backend/README.md describes: delete it, then ingest again.
    shutil.rmtree(store_dir / TEST_OBSERVATIONS.name)
    ingest(store_dir, TEST_OBSERVATIONS, T2, (date(2020, 4, 1), 1.5))
    new = write_manifest(store_dir, TABLES, now=T2)

    assert old is not None and new is not None
    with pytest.raises(DataVersionError, match="missing files it lists: test_obs"):
        values(store_dir, old.data_version)
    assert values(store_dir, new.data_version) == [1.5]


@pytest.mark.parametrize("same_size", [True, False])
def test_a_pinned_view_fails_clearly_when_a_file_changed(
    store_dir: Path, same_size: bool
) -> None:
    ingest(store_dir, TEST_OBSERVATIONS, T1, (date(2020, 4, 1), 1.0))
    version = write_manifest(store_dir, TABLES, now=T1)
    [file] = table_files(store_dir, TEST_OBSERVATIONS)
    content = file.read_bytes()

    # Flip the last byte, which only the hash notices, or add one.
    if same_size:
        file.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
    else:
        file.write_bytes(content + b"\0")

    assert version is not None
    with pytest.raises(DataVersionError, match="changed after it was cut"):
        values(store_dir, version.data_version)


def test_sizes_are_checked_on_every_open(store_dir: Path) -> None:
    ingest(store_dir, TEST_OBSERVATIONS, T1, (date(2020, 4, 1), 1.0))
    version = write_manifest(store_dir, TABLES, now=T1)
    assert version is not None
    assert values(store_dir, version.data_version) == [1.0]  # hashes checked once

    [file] = table_files(store_dir, TEST_OBSERVATIONS)
    file.write_bytes(file.read_bytes() + b"\0")

    with pytest.raises(DataVersionError, match="changed after it was cut"):
        values(store_dir, version.data_version)


def test_a_table_the_version_doesnt_list_reads_as_empty(store_dir: Path) -> None:
    ingest(store_dir, TEST_OBSERVATIONS, T1, (date(2020, 4, 1), 1.0))
    version = write_manifest(store_dir, TABLES, now=T1)
    ingest(store_dir, OTHER, T2, (date(2020, 4, 1), 3.0))  # a table filled later

    assert version is not None
    assert values(store_dir, version.data_version, OTHER.name) == []
    assert values(store_dir, None, OTHER.name) == [3.0]


def test_rows_ingested_later_stay_hidden_even_from_a_listed_file(
    store_dir: Path,
) -> None:
    ingest(store_dir, TEST_OBSERVATIONS, T1, (date(2020, 4, 1), 1.0))
    version = write_manifest(store_dir, TABLES, now=T1)
    ingest(store_dir, TEST_OBSERVATIONS, T2, (date(2020, 5, 1), 2.0))
    assert version is not None

    # Break the manifest by hand so it lists the later file too: the ingested_at
    # bound still hides that file's rows.
    path = store_dir / VERSIONS / f"{version.data_version}.json"
    content = json.loads(path.read_text(encoding="utf-8"))
    later = table_files(store_dir, TEST_OBSERVATIONS)[-1]
    content["tables"]["test_observations"]["files"].append(
        {"name": later.name, "size": later.stat().st_size, "sha256": sha256(later)}
    )
    path.write_text(json.dumps(content), encoding="utf-8")

    assert values(store_dir, version.data_version) == [1.0]
