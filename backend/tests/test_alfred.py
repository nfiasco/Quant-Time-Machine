import logging
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import httpx2
import pytest

from app.config import get_settings
from app.data.http import client_for
from app.data.sources import IngestContext, IngestError, alfred
from app.data.tables import MACRO_OBSERVATIONS
from app.data.timeutil import parse_knowledge_time
from app.data.view import PointInTimeView
from tests.fakes import FakeClock, FakeServer, fake_client, ok, settings

OPEN = "9999-12-31"


def version(day: str, value: str, start: str, end: str = OPEN) -> dict[str, str]:
    """One record of FRED's series/observations: a value and its real-time period."""
    return {"realtime_start": start, "realtime_end": end, "date": day, "value": value}


class FakeFred:
    """Answers FRED's series, series/release, and series/observations for the catalog.

    `observations` holds each series' versions (other series have none). `release_ids`
    and `metadata` override what FRED says about a series.
    """

    def __init__(
        self,
        observations: Mapping[str, list[dict[str, str]]],
        *,
        release_ids: Mapping[str, int] | None = None,
        metadata: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        self.observations = observations
        self.release_ids = dict(release_ids or {})
        self.metadata = dict(metadata or {})

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        params = request.url.params
        series = alfred.SERIES[params["series_id"]]
        match request.url.path.removeprefix("/fred/"):
            case "series/release":
                release_id = self.release_ids.get(
                    series.id, series.release.fred_release_id
                )
                return ok({"releases": [{"id": release_id, "name": "A release"}]})
            case "series":
                info = {
                    "id": series.id,
                    "title": series.title,
                    "units": series.units,
                    "frequency": series.frequency,
                    "seasonal_adjustment": series.seasonal_adjustment,
                }
                return ok({"seriess": [info | dict(self.metadata.get(series.id, {}))]})
            case "series/observations":
                records = self.observations.get(series.id, [])
                offset, limit = int(params["offset"]), int(params["limit"])
                return ok(
                    {
                        "count": len(records),
                        "offset": offset,
                        "limit": limit,
                        "observations": records[offset : offset + limit],
                    }
                )
        return httpx2.Response(404)


def ingest(tmp_path: Path, server: FakeServer) -> Path:
    store = tmp_path / "store"
    with fake_client(tmp_path, "fred", server, FakeClock()) as client:
        alfred.ingest(IngestContext(settings(tmp_path), client, store))
    return store


def stored(store: Path) -> list[dict[str, object]]:
    far_future = datetime(2098, 1, 1, tzinfo=UTC)
    with PointInTimeView(far_future, store=store, tables=[MACRO_OBSERVATIONS]) as view:
        return view._select("macro_observations")


def observations_requests(server: FakeServer) -> list[httpx2.Request]:
    return [r for r in server.requests if r.url.path.endswith("/series/observations")]


JANUARY_1990 = [
    version("1990-01-01", "5.3", "1990-02-02", "1996-03-07"),
    version("1990-01-01", "5.4", "1996-03-08"),
]


def test_each_version_becomes_a_row(tmp_path: Path) -> None:
    server = FakeServer(FakeFred({"UNRATE": JANUARY_1990}))

    rows = stored(ingest(tmp_path, server))

    assert [{k: v for k, v in r.items() if k != "ingested_at"} for r in rows] == [
        {
            "series_id": "UNRATE",
            "observation_date": date(1990, 1, 1),
            "value": 5.3,
            "vintage_date": date(1990, 2, 2),
            "source": "alfred",
            "source_ref": "UNRATE vintage 1990-02-02",
            # The jobs report's 08:30 in New York, EST in February.
            "available_at": datetime(1990, 2, 2, 13, 30, tzinfo=UTC),
            "time_assumed": False,
        },
        {
            "series_id": "UNRATE",
            "observation_date": date(1990, 1, 1),
            "value": 5.4,
            "vintage_date": date(1996, 3, 8),
            "source": "alfred",
            "source_ref": "UNRATE vintage 1996-03-08",
            "available_at": datetime(1996, 3, 8, 13, 30, tzinfo=UTC),
            "time_assumed": False,
        },
    ]


def test_a_missing_value_is_stored_as_none(tmp_path: Path) -> None:
    # Made up: FRED marks a published-but-missing value with ".".
    server = FakeServer(
        FakeFred({"FEDFUNDS": [version("2020-01-01", ".", "2020-02-03")]})
    )

    [row] = stored(ingest(tmp_path, server))

    assert row["series_id"] == "FEDFUNDS"
    assert row["value"] is None


def test_every_observations_request_asks_for_all_vintages(tmp_path: Path) -> None:
    server = FakeServer(FakeFred({"UNRATE": JANUARY_1990}))

    ingest(tmp_path, server)

    requests = observations_requests(server)
    assert len(requests) == len(alfred.SERIES)
    for request in requests:
        assert request.url.params["realtime_start"] == "1776-07-04"
        assert request.url.params["realtime_end"] == "9999-12-31"


def test_long_histories_are_read_page_by_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(alfred, "PAGE_SIZE", 2)
    months = [version(f"2020-0{m}-01", "4.0", f"2020-0{m + 1}-05") for m in range(1, 6)]
    server = FakeServer(FakeFred({"UNRATE": months}))

    rows = stored(ingest(tmp_path, server))

    unrate = [
        r
        for r in observations_requests(server)
        if r.url.params["series_id"] == "UNRATE"
    ]
    assert [r.url.params["offset"] for r in unrate] == ["0", "2", "4"]
    assert len(rows) == 5


def test_unrate_loads_first_then_the_other_five(tmp_path: Path) -> None:
    server = FakeServer(FakeFred({}))

    ingest(tmp_path, server)

    order = [r.url.params["series_id"] for r in observations_requests(server)]
    assert order == ["UNRATE", "PAYEMS", "CPIAUCSL", "GDP", "FEDFUNDS", "TB3MS"]
    assert server.requests[0].url.params["series_id"] == "UNRATE"


def test_rerunning_adds_nothing_and_makes_no_requests(tmp_path: Path) -> None:
    server = FakeServer(FakeFred({"UNRATE": JANUARY_1990}))
    store = ingest(tmp_path, server)
    requests = len(server.requests)

    ingest(tmp_path, server)

    assert len(server.requests) == requests  # answered from the raw cache
    assert len(list((store / "macro_observations").glob("part-*.parquet"))) == 1
    assert len(stored(store)) == 2


def test_a_different_release_stops_the_run(tmp_path: Path) -> None:
    server = FakeServer(FakeFred({"UNRATE": JANUARY_1990}, release_ids={"UNRATE": 99}))

    with pytest.raises(IngestError, match="release 99"):
        ingest(tmp_path, server)

    assert not (tmp_path / "store").exists()


def test_changed_metadata_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fred = FakeFred(
        {"UNRATE": JANUARY_1990}, metadata={"UNRATE": {"title": "Jobless Rate"}}
    )

    with caplog.at_level(logging.WARNING, logger="app.data.sources.alfred"):
        rows = stored(ingest(tmp_path, FakeServer(fred)))

    assert "UNRATE: FRED's title is 'Jobless Rate'" in caplog.text
    assert len(rows) == 2


def test_observations_dropped_by_later_vintages_are_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The only version ends in 1996, and no later vintage has the observation.
    server = FakeServer(FakeFred({"UNRATE": JANUARY_1990[:1]}))

    with caplog.at_level(logging.WARNING, logger="app.data.sources.alfred"):
        ingest(tmp_path, server)

    assert "UNRATE: 1 observations are missing from the latest vintages" in caplog.text


def test_the_catalog_lists_the_six_starter_series() -> None:
    releases = {s.id: s.release.name for s in alfred.SERIES.values()}

    assert releases == {
        "UNRATE": "Employment Situation",
        "PAYEMS": "Employment Situation",
        "CPIAUCSL": "Consumer Price Index",
        "GDP": "Gross Domestic Product",
        "FEDFUNDS": "H.15 Selected Interest Rates",
        "TB3MS": "H.15 Selected Interest Rates",
    }


def catalog_file(tmp_path: Path, release: str, series_release: str = "cpi") -> Path:
    """A one-series catalog whose release `cpi` has the given TOML lines."""
    path = tmp_path / "catalog.toml"
    path.write_text(
        f'[releases.cpi]\nname = "Consumer Price Index"\nfred_release_id = 10\n'
        f"{release}\n\n"
        '[[series]]\nid = "CPIAUCSL"\ntitle = "t"\nunits = "u"\nfrequency = "f"\n'
        f'seasonal_adjustment = "s"\nrelease = "{series_release}"\n',
        encoding="utf-8",
    )
    return path


def test_the_catalog_rejects_an_unknown_release(tmp_path: Path) -> None:
    path = catalog_file(tmp_path, 'time = "unknown"', series_release="jobs")

    with pytest.raises(ValueError, match="unknown release 'jobs'"):
        alfred.load_catalog(path)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_may_2020_unrate_known_at_0930_not_0800(tmp_path: Path) -> None:
    # The May 2020 jobs report came out at 08:30 ET on June 5 (doc/time-model.md).
    server = FakeServer(
        FakeFred(
            {
                "UNRATE": [
                    version("2020-04-01", "14.7", "2020-05-08"),
                    version("2020-05-01", "13.3", "2020-06-05"),
                ]
            }
        )
    )
    store = ingest(tmp_path, server)

    def latest(knowledge_time: str) -> tuple[object, object]:
        moment = parse_knowledge_time(knowledge_time)
        with PointInTimeView(moment, store=store, tables=[MACRO_OBSERVATIONS]) as view:
            [row] = view._select(
                "macro_observations",
                where="series_id = 'UNRATE'",
                latest_per_key=True,
                order_by="observation_date DESC",
                limit=1,
            )
        return row["observation_date"], row["value"]

    assert latest("2020-06-05T09:30") == (date(2020, 5, 1), 13.3)
    assert latest("2020-06-05T08:00") == (date(2020, 4, 1), 14.7)
    assert latest("2020-06-05T08:30") == (date(2020, 5, 1), 13.3)  # inclusive


def test_unknown_release_time_is_end_of_day_and_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unrate = alfred.SERIES["UNRATE"]
    unknown = replace(unrate.release, time_of_day=None, sources=(), exceptions={})
    monkeypatch.setitem(alfred.SERIES, "UNRATE", replace(unrate, release=unknown))
    server = FakeServer(
        FakeFred({"UNRATE": [version("2020-05-01", "13.3", "2020-06-01")]})
    )

    [row] = stored(ingest(tmp_path, server))

    # 23:59:59.999999 EDT on June 1, so the June 2 09:30 decision is the first to see it.
    assert row["available_at"] == utc(2020, 6, 2, 3, 59, 59, 999999)
    assert row["time_assumed"] is True


@pytest.mark.parametrize(
    ("series_id", "vintage", "known_at"),
    [
        ("UNRATE", date(1990, 2, 2), utc(1990, 2, 2, 13, 30)),  # 08:30 EST
        ("PAYEMS", date(2020, 6, 5), utc(2020, 6, 5, 12, 30)),  # 08:30 EDT
        ("CPIAUCSL", date(2020, 6, 10), utc(2020, 6, 10, 12, 30)),
        ("GDP", date(2020, 4, 29), utc(2020, 4, 29, 12, 30)),
        ("FEDFUNDS", date(2020, 6, 1), utc(2020, 6, 1, 20, 15)),  # 16:15 EDT
        ("TB3MS", date(2020, 1, 2), utc(2020, 1, 2, 21, 15)),  # 16:15 EST
    ],
)
def test_vintages_are_known_at_their_release_time(
    series_id: str, vintage: date, known_at: datetime
) -> None:
    release = alfred.SERIES[series_id].release

    assert alfred.vintage_known_at(release, vintage) == (known_at, False)


def test_the_october_1998_jobs_report_came_out_at_1330() -> None:
    # Scheduled for 08:30 on November 6, released at 1:30 PM EST on November 5.
    release = alfred.SERIES["UNRATE"].release

    assert alfred.vintage_known_at(release, date(1998, 11, 5)) == (
        utc(1998, 11, 5, 18, 30),
        False,
    )
    assert alfred.vintage_known_at(release, date(1998, 11, 6)) == (
        utc(1998, 11, 6, 13, 30),
        False,
    )


def test_every_release_time_cites_a_source() -> None:
    for series in alfred.SERIES.values():
        assert series.release.time_of_day is not None, series.id
        assert all(s.startswith("https://") for s in series.release.sources), series.id
        assert series.release.sources, series.id


def test_the_catalog_loads_an_unknown_time_as_none(tmp_path: Path) -> None:
    [series] = alfred.load_catalog(catalog_file(tmp_path, 'time = "unknown"')).values()

    assert series.release.time_of_day is None
    assert alfred.vintage_known_at(series.release, date(2020, 6, 1))[1] is True


AN_EXCEPTION = (
    'time = 08:30:00\nsources = ["https://example.com"]\n[[releases.cpi.exceptions]]\n'
)


@pytest.mark.parametrize(
    ("lines", "problem"),
    [
        ("", "needs a time"),
        ('time = "8:30"', "must look like 08:30:00"),
        ("time = 08:30:00", "needs sources"),
        (AN_EXCEPTION + "date = 2020-06-05\ntime = 13:30:00", "needs a source"),
        (
            AN_EXCEPTION + 'date = 2020-06-05T13:30:00\ntime = 13:30:00\nsource = "s"',
            "needs a date and a time",
        ),
    ],
)
def test_the_catalog_rejects_uncited_or_malformed_times(
    tmp_path: Path, lines: str, problem: str
) -> None:
    with pytest.raises(ValueError, match=problem):
        alfred.load_catalog(catalog_file(tmp_path, lines))


@pytest.mark.network
def test_live_catalog_and_january_1990(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # About 13 requests to FRED: each series' release and metadata, plus UNRATE's
    # observations. Checks the catalog against FRED and the golden case in the time
    # model: January 1990 was 5.3% from 1990-02-02 and 5.4% from 1996-03-08.
    live = get_settings()
    if live.fred_api_key is None:
        pytest.skip("FRED_API_KEY isn't set in backend/.env")

    with (
        client_for("fred", live.model_copy(update={"data_dir": tmp_path})) as client,
        caplog.at_level(logging.WARNING, logger="app.data.sources.alfred"),
    ):
        for series in alfred.SERIES.values():
            alfred.check_metadata(client, series)
        unrate = alfred.SERIES["UNRATE"]
        rows = alfred.vintage_rows(unrate, alfred.fetch_observations(client, unrate.id))

    assert caplog.text == ""  # the catalog's metadata matches FRED's
    january = [
        (r["value"], r["vintage_date"])
        for r in rows
        if r["observation_date"] == date(1990, 1, 1)
    ]
    assert january == [(5.3, date(1990, 2, 2)), (5.4, date(1996, 3, 8))]
    # Each exception day is a real UNRATE vintage, so none of them is dead config.
    assert set(unrate.release.exceptions) <= {r["vintage_date"] for r in rows}
