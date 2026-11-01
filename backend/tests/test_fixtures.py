from datetime import timedelta
from pathlib import Path

import pytest

from app.data.store import StoreError, connect, table_source
from app.data.versions import VERSIONS, latest_data_version, read_manifest
from tests.fixture_loader import (
    FIXTURE_DATA_VERSION,
    FIXTURE_INGESTED_AT,
    FIXTURES,
    TEST_OBSERVATIONS,
    load_fixture,
)


def test_timestamps_are_timezone_aware_utc(fixture_store: Path) -> None:
    with connect() as connection:
        rows = connection.execute(
            "SELECT available_at, ingested_at "
            f"FROM {table_source(fixture_store, TEST_OBSERVATIONS)}"
        ).fetchall()

    assert rows
    for available_at, ingested_at in rows:
        assert available_at.utcoffset() == timedelta(0)
        assert ingested_at.utcoffset() == timedelta(0)


def test_every_fixture_file_was_loaded(fixture_store: Path) -> None:
    loaded = {path.name for path in fixture_store.iterdir() if path.name != VERSIONS}

    assert loaded == {path.stem for path in FIXTURES.glob("*.csv")}


def test_the_fixture_store_is_one_data_version(fixture_store: Path) -> None:
    manifest = read_manifest(fixture_store, FIXTURE_DATA_VERSION)

    assert latest_data_version(fixture_store) == FIXTURE_DATA_VERSION
    assert set(manifest.tables) == {path.stem for path in FIXTURES.glob("*.csv")}
    assert manifest.ingested_through == FIXTURE_INGESTED_AT


def write_csv(path: Path, *rows: str) -> Path:
    header = "series_id,period,value,source,source_ref,available_at,time_assumed"
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


CANARY = "X,2020-05-01,1.0,test,canary,2099-01-01T00:00:00Z,false"


def test_fixture_timestamps_need_an_offset(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "test_observations.csv",
        "X,2020-05-01,1.0,test,naive,2020-06-05T12:30:00,false",
        CANARY,
    )

    with pytest.raises(ValueError, match="naive"):
        load_fixture(tmp_path / "store", TEST_OBSERVATIONS, path)


def test_fixture_files_need_a_canary_row(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "test_observations.csv",
        "X,2020-05-01,1.0,test,ok,2020-06-05T12:30:00Z,false",
    )

    with pytest.raises(pytest.fail.Exception, match="canary"):
        load_fixture(tmp_path / "store", TEST_OBSERVATIONS, path)


def test_fixture_columns_must_match_the_table(tmp_path: Path) -> None:
    path = tmp_path / "test_observations.csv"
    path.write_text(
        "series_id,period,value,source,source_ref,available_at,time_assumed,ingested_at\n"
        f"{CANARY},2026-10-19T00:00:00Z\n",
        encoding="utf-8",
    )

    with pytest.raises(StoreError, match="ingested_at"):
        load_fixture(tmp_path / "store", TEST_OBSERVATIONS, path)
