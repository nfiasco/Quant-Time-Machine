from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.data.store import (
    StoreError,
    TableSpec,
    connect,
    sql_string,
    table_files,
    table_source,
    write_rows,
)

SPEC = TableSpec(
    name="observations",
    key=("series_id", "period"),
    columns={"series_id": "VARCHAR", "period": "DATE", "value": "DOUBLE"},
)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def row(**changes: object) -> dict[str, object]:
    """May 2020 unemployment as first printed, with any fields changed."""
    return {
        "series_id": "UNRATE",
        "period": date(2020, 5, 1),
        "value": 13.3,
        "source": "fred",
        "source_ref": "UNRATE vintage 2020-06-05",
        "available_at": utc(2020, 6, 5, 12, 30),
        "time_assumed": False,
    } | changes


def stored_rows(store: Path, spec: TableSpec = SPEC) -> list[dict[str, object]]:
    with connect() as connection:
        cursor = connection.execute(f"SELECT * FROM {table_source(store, spec)}")
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]


def test_stored_timestamps_are_aware_utc(tmp_path: Path) -> None:
    write_rows(tmp_path, SPEC, [row()], now=utc(2026, 10, 19, 12))

    [stored] = stored_rows(tmp_path)

    for column in ("available_at", "ingested_at"):
        assert stored[column].utcoffset() == timedelta(0)
    assert stored["available_at"] == utc(2020, 6, 5, 12, 30)
    assert stored["ingested_at"] == utc(2026, 10, 19, 12)


def test_rows_round_trip_with_their_types(tmp_path: Path) -> None:
    result = write_rows(tmp_path, SPEC, [row(value=None, time_assumed=True)])

    assert result.written == 1
    assert result.path is not None
    assert result.path.parent == tmp_path / "observations"
    [stored] = stored_rows(tmp_path)
    assert stored["period"] == date(2020, 5, 1)
    assert stored["value"] is None  # NULL, not NaN
    assert stored["time_assumed"] is True
    assert stored["source_ref"] == "UNRATE vintage 2020-06-05"


def test_other_offsets_are_stored_in_utc(tmp_path: Path) -> None:
    edt = timezone(timedelta(hours=-4))
    write_rows(
        tmp_path, SPEC, [row(available_at=datetime(2020, 6, 5, 8, 30, tzinfo=edt))]
    )

    [stored] = stored_rows(tmp_path)

    assert stored["available_at"] == utc(2020, 6, 5, 12, 30)


def test_files_are_sorted_by_key_and_available_at(tmp_path: Path) -> None:
    rows = [
        row(period=date(2020, 5, 1), value=13.2, available_at=utc(2020, 7, 2, 12, 30)),
        row(period=date(2020, 4, 1), value=14.7, available_at=utc(2020, 5, 8, 12, 30)),
        row(period=date(2020, 5, 1)),
    ]

    result = write_rows(tmp_path, SPEC, rows)

    assert result.path is not None
    with connect() as connection:
        order = connection.execute(
            f"SELECT period, available_at FROM read_parquet({sql_string(str(result.path))})"
        ).fetchall()
    assert order == sorted(order)


def test_rerunning_the_same_rows_writes_nothing(tmp_path: Path) -> None:
    write_rows(tmp_path, SPEC, [row(), row(period=date(2020, 4, 1), value=14.7)])

    again = write_rows(
        tmp_path, SPEC, [row(), row(period=date(2020, 4, 1), value=14.7)]
    )

    assert (again.written, again.skipped, again.conflicts, again.path) == (
        0,
        2,
        0,
        None,
    )
    assert len(table_files(tmp_path, SPEC)) == 1
    assert len(stored_rows(tmp_path)) == 2


def test_a_revision_is_a_new_row(tmp_path: Path) -> None:
    write_rows(tmp_path, SPEC, [row()])

    revised = row(value=13.2, available_at=utc(2020, 7, 2, 12, 30))
    result = write_rows(tmp_path, SPEC, [row(), revised])

    assert (result.written, result.skipped) == (1, 1)
    assert sorted(r["value"] for r in stored_rows(tmp_path)) == [13.2, 13.3]
    assert len(table_files(tmp_path, SPEC)) == 2


def test_a_changed_value_is_a_conflict_and_the_stored_row_wins(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_rows(tmp_path, SPEC, [row()])

    result = write_rows(tmp_path, SPEC, [row(value=99.9)])

    assert (result.written, result.skipped, result.conflicts) == (0, 0, 1)
    assert [r["value"] for r in stored_rows(tmp_path)] == [13.3]
    assert "kept 1 stored rows" in caplog.text


def test_exact_duplicates_in_a_batch_collapse(tmp_path: Path) -> None:
    result = write_rows(tmp_path, SPEC, [row(), row()])

    assert result.written == 1


def test_conflicting_duplicates_in_a_batch_raise(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="share a key and available_at"):
        write_rows(tmp_path, SPEC, [row(), row(value=13.2)])

    assert table_files(tmp_path, SPEC) == []


def test_naive_datetimes_are_rejected(tmp_path: Path) -> None:
    naive = datetime(2020, 6, 5, 8, 30)  # noqa: DTZ001 (naive on purpose)

    with pytest.raises(StoreError, match="naive datetime"):
        write_rows(tmp_path, SPEC, [row(available_at=naive)])


@pytest.mark.parametrize(
    ("bad_row", "message"),
    [
        ({k: v for k, v in row().items() if k != "time_assumed"}, "missing columns"),
        (row(note="extra"), "unexpected columns"),
        (row(ingested_at=utc(2026, 10, 19)), "don't pass ingested_at"),
        (row(series_id=None), "series_id can't be empty"),
        (row(source_ref=None), "source_ref can't be empty"),
        (row(source=""), "can't be blank"),
        (row(value="13.3"), "isn't a valid DOUBLE"),
        (row(value=float("nan")), "isn't a valid DOUBLE"),
        (row(period=utc(2020, 5, 1)), "isn't a valid DATE"),
        (row(time_assumed="no"), "isn't a valid BOOLEAN"),
    ],
)
def test_invalid_rows_are_rejected(
    tmp_path: Path, bad_row: dict[str, object], message: str
) -> None:
    with pytest.raises(StoreError, match=message):
        write_rows(tmp_path, SPEC, [bad_row])


def test_an_empty_table_reads_as_no_rows(tmp_path: Path) -> None:
    assert stored_rows(tmp_path) == []
    assert write_rows(tmp_path, SPEC, []).written == 0
    assert not (tmp_path / "observations").exists()


def test_no_temporary_files_are_left_behind(tmp_path: Path) -> None:
    write_rows(tmp_path, SPEC, [row()])

    leftovers = [p.name for p in (tmp_path / "observations").iterdir()]

    assert len(leftovers) == 1
    assert leftovers[0].startswith("part-")
    assert leftovers[0].endswith(".parquet")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "Bad Name"}, "not lowercase identifiers"),
        ({"key": ("missing",)}, "key must be"),
        ({"columns": {"series_id": "VARCHAR", "source": "VARCHAR"}}, "provenance"),
        ({"columns": {"series_id": "VARCHAR", "period": "TEXT"}}, "unsupported"),
    ],
)
def test_table_specs_are_checked(kwargs: dict[str, object], message: str) -> None:
    spec = {"name": "observations", "key": ("series_id",), "columns": SPEC.columns}

    with pytest.raises(ValueError, match=message):
        TableSpec(**(spec | kwargs))
