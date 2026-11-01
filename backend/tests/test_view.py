import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.data.errors import LookAheadError
from app.data.store import write_rows
from app.data.tables import TABLES
from app.data.versions import write_manifest
from app.data.view import AccessRecord, PointInTimeView
from tests.fixture_loader import (
    CANARY_YEAR,
    FIXTURE_DATA_VERSION,
    FIXTURE_INGESTED_AT,
    TEST_OBSERVATIONS,
    TEST_TABLES,
)

ALL_TABLES = TABLES | TEST_TABLES
APP_DIR = Path(__file__).resolve().parents[1] / "app"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


DEMO = utc(2020, 6, 5, 13, 30)  # June 5, 2020, at 09:30 ET


def view_at(store: Path, knowledge_time: datetime) -> PointInTimeView:
    return PointInTimeView(knowledge_time, store=store, tables=ALL_TABLES.values())


def latest(view: PointInTimeView, period: date) -> float | None:
    rows = view._select(
        "test_observations",
        where="series_id = ? AND period = ?",
        params=["TEST", period],
        latest_per_key=True,
    )
    return rows[0]["value"] if rows else None


@pytest.mark.parametrize(
    "knowledge_time",
    [DEMO, utc(2026, 10, 19), utc(CANARY_YEAR, 1, 1) - timedelta(microseconds=1)],
)
def test_poisoned_future_row_never_returned(
    fixture_store: Path, knowledge_time: datetime
) -> None:
    # Every fixture table has a row available in 2099 (tests/fixtures/README.md).
    with view_at(fixture_store, knowledge_time) as view:
        for table in ALL_TABLES:
            for latest_per_key in (False, True):
                rows = view._select(table, latest_per_key=latest_per_key)
                assert all(r["available_at"] <= knowledge_time for r in rows)
            # Not even raw SQL on the view's own connection can reach the row.
            (newest,) = view._connection.execute(
                f"SELECT max(available_at) FROM {table}"
            ).fetchone() or (None,)
            assert newest is None or newest.year < CANARY_YEAR


def test_canary_rows_are_really_in_the_store(fixture_store: Path) -> None:
    # Without this, the test above would pass on an empty store.
    with view_at(fixture_store, utc(CANARY_YEAR, 1, 1)) as view:
        for table in ALL_TABLES:
            rows = view._select(table)
            assert any(r["available_at"].year >= CANARY_YEAR for r in rows)


def test_a_row_is_visible_from_its_available_at(fixture_store: Path) -> None:
    published = utc(2020, 6, 5, 12, 30)  # May's first print

    with view_at(fixture_store, published) as view:
        assert latest(view, date(2020, 5, 1)) == 101.0
    with view_at(fixture_store, published - timedelta(microseconds=1)) as view:
        assert latest(view, date(2020, 5, 1)) is None


def test_latest_version_per_key(fixture_store: Path) -> None:
    def latest_values(knowledge_time: datetime) -> list[tuple[object, object]]:
        with view_at(fixture_store, knowledge_time) as view:
            rows = view._select(
                "test_observations",
                where="series_id = ?",
                params=["TEST"],
                latest_per_key=True,
            )
        return [(r["period"], r["value"]) for r in rows]

    assert latest_values(DEMO) == [(date(2020, 4, 1), 100.0), (date(2020, 5, 1), 101.0)]
    # After the revision on July 2, May's value is the revised one.
    assert latest_values(utc(2020, 7, 2, 13, 30)) == [
        (date(2020, 4, 1), 100.0),
        (date(2020, 5, 1), 101.5),
        (date(2020, 6, 1), 102.0),
    ]


def test_latest_where_looks_only_at_each_keys_latest_version(
    fixture_store: Path,
) -> None:
    # On July 2, May's 101.0 was revised to 101.5. A `where` filters versions before
    # the latest is picked, so it still finds the old value; `latest_where` doesn't.
    with view_at(fixture_store, utc(2020, 7, 2, 13, 30)) as view:
        stale = view._select(
            "test_observations",
            where="value = ?",
            params=[101.0],
            latest_per_key=True,
        )
        current = view._select(
            "test_observations",
            params=[101.0],
            latest_per_key=True,
            latest_where="value = ?",
        )

    assert [r["value"] for r in stale] == [101.0]
    assert current == []


def test_latest_where_needs_latest_per_key(store_dir: Path) -> None:
    with (
        PointInTimeView(DEMO, store=store_dir, tables=[TEST_OBSERVATIONS]) as view,
        pytest.raises(ValueError, match="latest_per_key"),
    ):
        view._select("test_observations", latest_where="true")


def test_all_versions_known_so_far(fixture_store: Path) -> None:
    with view_at(fixture_store, utc(2020, 7, 2, 13, 30)) as view:
        rows = view._select(
            "test_observations",
            where="series_id = ? AND period = ?",
            params=["TEST", date(2020, 5, 1)],
        )

    assert [r["value"] for r in rows] == [101.0, 101.5]


def test_access_log_records_every_row_read(fixture_store: Path) -> None:
    with view_at(fixture_store, DEMO) as view:
        latest(view, date(2020, 5, 1))
        latest(view, date(2020, 6, 1))  # not known yet: nothing to log

        assert view.access_log == (
            AccessRecord(
                table="test_observations",
                key=("TEST", date(2020, 5, 1)),
                available_at=utc(2020, 6, 5, 12, 30),
                source_ref="synthetic: May first print",
            ),
        )


def test_rows_come_back_with_utc_datetimes(fixture_store: Path) -> None:
    with view_at(fixture_store, DEMO) as view:
        [row] = view._select("test_observations", where="series_id = 'TEST_EOD'")

    assert row["available_at"] == utc(2020, 6, 2, 3, 59, 59, 999999)
    assert row["available_at"].tzinfo is UTC
    assert row["time_assumed"] is True
    assert row["value"] is None


def test_require_known_by_raises_look_ahead_error(store_dir: Path) -> None:
    with view_at(store_dir, DEMO) as view:
        view._require_known_by(utc(2020, 6, 4, 20), "the 2020-06-04 close")
        view._require_known_by(DEMO, "something known exactly at T")
        with pytest.raises(LookAheadError, match="isn't known until") as caught:
            view._require_known_by(utc(2020, 6, 5, 20), "the 2020-06-05 close")

    assert caught.value.knowledge_time == DEMO
    assert caught.value.data_version is None


def test_an_empty_store_reads_nothing(store_dir: Path) -> None:
    with PointInTimeView(DEMO, store=store_dir, tables=[TEST_OBSERVATIONS]) as view:
        assert view._select("test_observations", latest_per_key=True) == []


def test_naive_knowledge_times_are_rejected(store_dir: Path) -> None:
    naive = datetime(2020, 6, 5, 9, 30)  # noqa: DTZ001 (naive on purpose)

    with pytest.raises(ValueError, match="naive"):
        PointInTimeView(naive, store=store_dir, tables=[])


def test_pinned_data_version_ignores_later_rows(fixture_store: Path) -> None:
    # A later run revises May 2020 again and adds July (made up), then cuts a version.
    later = FIXTURE_INGESTED_AT + timedelta(days=1)
    known_on = utc(2020, 8, 7, 12, 30)
    write_rows(
        fixture_store,
        TEST_OBSERVATIONS,
        [
            {
                "series_id": "TEST",
                "period": period,
                "value": value,
                "source": "test",
                "source_ref": f"synthetic: ingested later, {period:%B}",
                "available_at": known_on,
                "time_assumed": False,
            }
            for period, value in ((date(2020, 5, 1), 101.7), (date(2020, 7, 1), 103.0))
        ],
        now=later,
    )
    newer = write_manifest(fixture_store, ALL_TABLES.values(), now=later)

    def may_and_july(data_version: str | None) -> list[float | None]:
        with PointInTimeView(
            utc(2026, 1, 1),
            data_version=data_version,
            store=fixture_store,
            tables=ALL_TABLES.values(),
        ) as view:
            assert view.data_version == data_version
            return [latest(view, date(2020, 5, 1)), latest(view, date(2020, 7, 1))]

    # The fixtures' version still answers as it did before the later run.
    assert may_and_july(FIXTURE_DATA_VERSION) == [101.5, None]
    assert newer is not None and newer.data_version == "20261020T120000Z"
    assert may_and_july(newer.data_version) == [101.7, 103.0]
    assert may_and_july(None) == [101.7, 103.0]  # unpinned: every file stored now


def test_unknown_tables_are_rejected(store_dir: Path) -> None:
    with (
        PointInTimeView(DEMO, store=store_dir, tables=[]) as view,
        pytest.raises(ValueError, match="no table named"),
    ):
        view._select("prices")


def test_only_the_store_module_touches_duckdb_and_parquet() -> None:
    # Reads must go through PointInTimeView, so nothing else may open DuckDB or Parquet.
    pattern = re.compile(r"\bread_parquet\b|\bimport duckdb\b|\bduckdb\.connect\b")
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if path.name != "store.py" and pattern.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []
