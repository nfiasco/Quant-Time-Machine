from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.data.errors import NotFoundError
from app.data.records import MacroObservation
from app.data.timeutil import parse_knowledge_time
from app.data.view import AccessRecord, PointInTimeView

JANUARY_1990 = date(1990, 1, 1)


def view_at(store: Path, knowledge_time: str) -> PointInTimeView:
    """A view of the fixture store at an `as_of`-style time (New York time)."""
    return PointInTimeView(parse_knowledge_time(knowledge_time), store=store)


def read(
    store: Path,
    knowledge_time: str,
    series_id: str = "UNRATE",
    period: date | None = None,
) -> MacroObservation | None:
    with view_at(store, knowledge_time) as view:
        return view.get_macro_as_of(series_id, period)


def value(
    store: Path,
    knowledge_time: str,
    series_id: str = "UNRATE",
    period: date | None = None,
) -> float | None:
    """The value read, or None if nothing had been published yet."""
    observation = read(store, knowledge_time, series_id, period)
    return None if observation is None else observation.value


@pytest.mark.parametrize(
    ("knowledge_time", "expected"),
    [
        ("1990-02-02T08:29:59", None),  # just before the first print
        ("1990-02-02T08:30", 5.3),  # the jobs report at 08:30 ET (inclusive)
        ("1996-03-07T23:59", 5.3),  # the day before the revision
        ("1996-03-08T08:29", 5.3),
        ("1996-03-08T08:30", 5.4),  # the revision's release
        ("2020-06-05", 5.4),
    ],
)
def test_macro_first_print_vs_revision_jan_1990(
    fixture_store: Path, knowledge_time: str, expected: float | None
) -> None:
    # January 1990 was first published as 5.3% and revised to 5.4% in March 1996.
    assert value(fixture_store, knowledge_time, period=JANUARY_1990) == expected


def test_june_5_2020_sees_may_at_0930_and_april_at_0800(fixture_store: Path) -> None:
    at_0930 = read(fixture_store, "2020-06-05T09:30")
    at_0800 = read(fixture_store, "2020-06-05T08:00")

    # The record doc/api-v1.md shows for GET /v1/macro/UNRATE?as_of=2020-06-05.
    assert at_0930 == MacroObservation(
        series_id="UNRATE",
        title="Unemployment Rate",
        units="Percent",
        frequency="Monthly",
        seasonal_adjustment="Seasonally Adjusted",
        release="Employment Situation",
        period=date(2020, 5, 1),
        value=13.3,
        vintage_date=date(2020, 6, 5),
        available_at=datetime(2020, 6, 5, 12, 30, tzinfo=UTC),
        time_assumed=False,
        source="alfred",
        source_ref="UNRATE vintage 2020-06-05",
    )
    assert at_0800 is not None
    assert (at_0800.period, at_0800.value, at_0800.vintage_date) == (
        date(2020, 4, 1),
        14.7,
        date(2020, 5, 8),
    )


def test_a_revision_counts_from_its_own_release(fixture_store: Path) -> None:
    # May 2020 was 13.3% until the January 2022 jobs report revised it to 13.2%.
    may = date(2020, 5, 1)

    assert value(fixture_store, "2022-01-07T08:29", period=may) == 13.3
    assert value(fixture_store, "2022-01-07T08:30", period=may) == 13.2


def test_values_before_the_first_vintage_are_unknown_until_it(
    fixture_store: Path,
) -> None:
    # ALFRED's GDP history starts with the vintage of December 4, 1991, so the first
    # quarter of 1985 counts as unknown until then.
    first_quarter = date(1985, 1, 1)

    assert read(fixture_store, "1990-01-02", "GDP") is None
    assert read(fixture_store, "1991-12-04T08:29", "GDP", first_quarter) is None
    assert value(fixture_store, "1991-12-04T08:30", "GDP", first_quarter) == 3940.0


def test_the_october_1998_report_counts_from_1330(fixture_store: Path) -> None:
    # Released at 1:30 PM EST on November 5, 1998, not at the usual 08:30 (S4.3).
    october = date(1998, 10, 1)

    assert read(fixture_store, "1998-11-05T13:29", period=october) is None
    assert value(fixture_store, "1998-11-05T13:30", period=october) == 4.6


def test_the_series_as_it_looked_on_june_5_2020(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-06-05") as view:
        series = view.get_macro_series_as_of("UNRATE", start=date(2020, 1, 1))

    # No June yet: its first print came on July 2.
    assert [(o.period, o.value) for o in series] == [
        (date(2020, 3, 1), 4.4),
        (date(2020, 4, 1), 14.7),
        (date(2020, 5, 1), 13.3),
    ]


def test_the_series_takes_each_observations_latest_version(fixture_store: Path) -> None:
    # By June 2021, April had been revised to 14.8%, and June's first print was out.
    with view_at(fixture_store, "2021-06-01") as view:
        series = view.get_macro_series_as_of(
            "UNRATE", start=date(2020, 4, 1), end=date(2020, 6, 1)
        )

    assert [(o.period, o.value, o.vintage_date) for o in series] == [
        (date(2020, 4, 1), 14.8, date(2021, 1, 8)),
        (date(2020, 5, 1), 13.3, date(2020, 6, 5)),
        (date(2020, 6, 1), 11.1, date(2020, 7, 2)),
    ]


def test_the_whole_series_is_the_default(fixture_store: Path) -> None:
    with view_at(fixture_store, "1996-03-08T09:30") as view:
        series = view.get_macro_series_as_of("UNRATE")

    assert [(o.period, o.value) for o in series] == [(JANUARY_1990, 5.4)]


def test_a_value_published_as_missing_reads_as_none(fixture_store: Path) -> None:
    # ALFRED has October 2025's unemployment rate as "." in the vintage of December
    # 16, 2025: published, but with no value.
    observation = read(fixture_store, "2025-12-16T09:30", period=date(2025, 10, 1))

    assert observation is not None
    assert observation.value is None
    assert observation.vintage_date == date(2025, 12, 16)


def test_a_future_row_never_reaches_a_read(fixture_store: Path) -> None:
    # The fixture's canary version of January 1990 (99.9) is published in 2099.
    assert value(fixture_store, "2098-12-31", period=JANUARY_1990) == 5.4


def test_series_ids_match_in_any_case(fixture_store: Path) -> None:
    observation = read(fixture_store, "2020-06-05", "unrate")

    assert observation is not None
    assert observation.series_id == "UNRATE"


def test_a_catalog_series_with_nothing_published_yet_reads_as_empty(
    fixture_store: Path,
) -> None:
    # PAYEMS is in the catalog, but the fixtures have none of its vintages.
    with view_at(fixture_store, "2020-06-05") as view:
        assert view.get_macro_as_of("PAYEMS") is None
        assert view.get_macro_series_as_of("PAYEMS") == []


def test_a_series_outside_the_catalog_is_not_found(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-06-05") as view:
        with pytest.raises(NotFoundError, match="unknown series: DGS10"):
            view.get_macro_as_of("DGS10")
        with pytest.raises(NotFoundError, match="unknown series: DGS10"):
            view.get_macro_series_as_of("DGS10")


def test_reads_are_in_the_access_log(fixture_store: Path) -> None:
    with view_at(fixture_store, "2020-06-05") as view:
        view.get_macro_as_of("UNRATE")

        assert view.access_log == (
            AccessRecord(
                table="macro_observations",
                key=("UNRATE", date(2020, 5, 1)),
                available_at=datetime(2020, 6, 5, 12, 30, tzinfo=UTC),
                source_ref="UNRATE vintage 2020-06-05",
            ),
        )
