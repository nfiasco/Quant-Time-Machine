import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from app.config import get_settings
from app.data.http import client_for
from app.data.sources import IngestContext, edgar, universes
from app.data.sources.edgar import (
    acceptance,
    corrected_acceptance,
    fetch_filings,
    filing_rows,
    runs_ahead,
)
from app.data.view import PointInTimeView
from tests.fakes import FakeClock, FakeServer, fake_client, ok, settings

Filing = tuple[str, str, str, str, str]
"""Accession number, form, filing date, report date, and acceptanceDateTime."""

COLUMNS = ("accessionNumber", "form", "filingDate", "reportDate", "acceptanceDateTime")


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def block(*filings: Filing) -> dict[str, list[str]]:
    """Filings in the submissions API's columnar format."""
    columns: dict[str, list[str]] = {name: [] for name in COLUMNS}
    columns |= {"primaryDocument": [], "items": []}
    for filing in filings:
        for name, value in zip(COLUMNS, filing, strict=True):
            columns[name].append(value)
        columns["primaryDocument"].append(f"{filing[0]}.htm")
        columns["items"].append("")
    return columns


class FakeEdgar:
    """Answers SEC's ticker file and submissions requests.

    `histories` maps a CIK to its recent block, then any older pages; companies not
    listed have no filings.
    """

    def __init__(self, histories: Mapping[int, Sequence[Sequence[Filing]]]) -> None:
        self.histories = histories

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        path = request.url.path
        if path == "/files/company_tickers.json":
            return ok({})
        name = path.removeprefix("/submissions/").removesuffix(".json")
        cik = int(name[3:13])
        recent, *pages = self.histories.get(cik, [()])
        if "-submissions-" in name:
            return ok(block(*pages[int(name[-3:]) - 1]))
        files = [
            {"name": f"CIK{cik:010d}-submissions-{n:03d}.json"}
            for n in range(1, len(pages) + 1)
        ]
        return ok(
            {"cik": str(cik), "filings": {"recent": block(*recent), "files": files}}
        )


@pytest.mark.parametrize(
    ("raw", "true_utc"),
    [
        ("2020-05-01T02:03:10.000Z", utc(2020, 4, 30, 22, 3, 10)),  # 18:03:10 EDT
        ("2020-01-29T04:02:44.000Z", utc(2020, 1, 28, 23, 2, 44)),  # 18:02:44 EST
    ],
)
def test_edgar_acceptance_time_correction(raw: str, true_utc: datetime) -> None:
    # Apple's fiscal Q2 and Q1 2020 10-Qs: the JSON runs ahead by the Eastern offset.
    assert corrected_acceptance(raw) == true_utc


# Apple's 10-Qs, whose JSON runs ahead: only the corrected reading explains their dates.
APPLE = [
    (
        "0000320193-20-000010",
        "10-Q",
        "2020-01-29",
        "2019-12-28",
        "2020-01-29T04:02:44.000Z",
    ),
    (
        "0000320193-20-000052",
        "10-Q",
        "2020-05-01",
        "2020-03-28",
        "2020-05-01T02:03:10.000Z",
    ),
    (
        "0000320193-20-000062",
        "10-Q",
        "2020-07-31",
        "2020-06-27",
        "2020-07-31T03:29:09.000Z",
    ),
]
# Twitter's 8-Ks, whose JSON is true UTC (EDGAR's index pages say 06:06:33, 08:15:57,
# and 20:22:36 ET): subtracting the offset would put them before EDGAR opens, or on
# the wrong filing date.
TWITTER = [
    (
        "0001193125-22-242335",
        "8-K",
        "2022-09-12",
        "2022-09-12",
        "2022-09-12T10:06:33.000Z",
    ),
    (
        "0001193125-22-244289",
        "8-K",
        "2022-09-14",
        "2022-09-14",
        "2022-09-14T12:15:57.000Z",
    ),
    (
        "0001193125-22-272772",
        "8-K",
        "2022-10-31",
        "2022-10-28",
        "2022-10-29T00:22:36.000Z",
    ),
]


def as_filings(*filings: Filing) -> list[dict[str, str]]:
    return [dict(zip(COLUMNS, filing, strict=True)) for filing in filings]


def test_a_company_whose_times_run_ahead_is_corrected() -> None:
    filings = as_filings(*APPLE)

    shifted, votes = runs_ahead(filings)
    rows = filing_rows(320193, filings, shifted=shifted)

    assert (shifted, votes) == (True, (3, 0))
    assert [(r["accession_number"], r["available_at"]) for r in rows] == [
        ("0000320193-20-000010", utc(2020, 1, 28, 23, 2, 44)),
        ("0000320193-20-000052", utc(2020, 4, 30, 22, 3, 10)),
        ("0000320193-20-000062", utc(2020, 7, 30, 23, 29, 9)),
    ]
    assert not any(r["time_assumed"] for r in rows)


def test_a_company_whose_times_are_true_utc_is_left_alone() -> None:
    filings = as_filings(*TWITTER)

    shifted, votes = runs_ahead(filings)
    rows = filing_rows(1418091, filings, shifted=shifted)

    assert (shifted, votes) == (False, (0, 3))
    assert [r["available_at"] for r in rows] == [
        utc(2022, 9, 12, 10, 6, 33),
        utc(2022, 9, 14, 12, 15, 57),
        utc(2022, 10, 29, 0, 22, 36),  # 20:22:36 EDT on Friday, dated Monday
    ]


def test_without_a_majority_times_are_read_as_shown() -> None:
    # Read as shown, a file that really runs ahead only makes its filings seem later
    # than they were, never earlier (rule 11). A date-only placeholder can't tell the
    # two readings apart.
    placeholder = (
        "0000912057-01-544436",
        "10-K405",
        "2001-12-21",
        "2001-09-29",
        "2001-12-21T10:00:00.000Z",
    )

    assert runs_ahead([]) == (False, (0, 0))
    assert runs_ahead(as_filings(placeholder)) == (False, (0, 0))
    assert runs_ahead(as_filings(APPLE[0], TWITTER[0])) == (False, (1, 1))


def test_either_form_of_a_file_gives_the_same_times() -> None:
    # By 2026-10-31, SEC serves the acceptance times it used to shift in true UTC.
    fixed = [
        (*f[:4], f"{corrected_acceptance(f[4]):%Y-%m-%dT%H:%M:%S}.000Z") for f in APPLE
    ]

    def times(filings: list[dict[str, str]]) -> list[datetime]:
        shifted, _ = runs_ahead(filings)
        return [
            r["available_at"] for r in filing_rows(320193, filings, shifted=shifted)
        ]

    assert runs_ahead(as_filings(*fixed)) == (False, (0, 3))
    assert times(as_filings(*fixed)) == times(as_filings(*APPLE))


@pytest.mark.parametrize(
    ("raw", "filed", "expected"),
    [
        # 1994 to 2002: a date-only placeholder, midnight ET once corrected.
        (
            "2001-12-21T10:00:00.000Z",
            "2001-12-21",
            utc(2001, 12, 22, 4, 59, 59, 999999),
        ),
        # No acceptance time at all.
        ("", "2001-12-21", utc(2001, 12, 22, 4, 59, 59, 999999)),
        # Accepted days after its filing date (a JPMorgan 10-K/A): the later time.
        ("2006-07-04T01:15:33.000Z", "2006-06-22", utc(2006, 7, 3, 21, 15, 33)),
    ],
)
def test_times_that_cant_be_right_are_assumed(
    raw: str, filed: str, expected: datetime
) -> None:
    assert acceptance(raw, date.fromisoformat(filed), shifted=True) == (expected, True)


def test_only_10k_10q_and_8k_filings_and_amendments_are_kept() -> None:
    forms = ["10-K", "10-K405", "10-KT/A", "10-Q", "10-QT", "8-K", "8-K/A", "10-K/A"]
    dropped = ["424B2", "4", "S-8", "8-K12B", "DEF 14A", "SC 13G"]
    filings = [
        (
            f"0000000001-20-{n:06d}",
            form,
            "2020-06-01",
            "2020-03-31",
            "2020-06-01T20:00:00.000Z",
        )
        for n, form in enumerate(forms + dropped)
    ]

    rows = filing_rows(1, as_filings(*filings), shifted=True)

    assert [r["form"] for r in rows] == forms


def test_amendments_link_to_the_latest_original_before_them() -> None:
    filings = as_filings(
        ("A-1", "10-Q", "2020-05-01", "2020-03-28", "2020-05-01T02:03:10.000Z"),
        ("A-2", "10-Q/A", "2020-06-10", "2020-03-28", "2020-06-11T00:00:00.000Z"),
        ("A-3", "10-Q/A", "2020-07-01", "2020-03-28", "2020-07-02T00:00:00.000Z"),
        ("B-1", "8-K", "2020-04-30", "2020-04-30", "2020-05-01T00:30:41.000Z"),
        ("B-2", "8-K/A", "2020-05-04", "2020-04-30", "2020-05-04T23:00:00.000Z"),
        ("C-1", "10-K/A", "2020-11-02", "2020-09-26", "2020-11-02T23:00:00.000Z"),
    )

    rows = filing_rows(320193, filings, shifted=True)

    assert {r["accession_number"]: r["amends"] for r in rows if r["is_amendment"]} == {
        "A-2": "A-1",
        "A-3": "A-1",  # an amendment amends the original, not the earlier amendment
        "B-2": "B-1",
        "C-1": None,  # no 10-K for that period in this history
    }


def test_older_pages_are_followed(tmp_path: Path) -> None:
    server = FakeServer(FakeEdgar({320193: [APPLE[2:], APPLE[1:2], APPLE[:1]]}))

    with fake_client(tmp_path, "sec", server, FakeClock()) as client:
        filings = fetch_filings(client, 320193)

    assert [str(r.url.path) for r in server.requests] == [
        "/submissions/CIK0000320193.json",
        "/submissions/CIK0000320193-submissions-001.json",
        "/submissions/CIK0000320193-submissions-002.json",
    ]
    assert sorted(f["accessionNumber"] for f in filings) == [f[0] for f in APPLE]


def test_requests_stay_within_10_per_second(tmp_path: Path) -> None:
    clock = FakeClock()
    times: list[datetime] = []
    edgar_server = FakeEdgar({320193: [APPLE[:1]] + [APPLE[1:2]] * 14})

    def server(request: httpx2.Request) -> httpx2.Response:
        times.append(clock.now)
        return edgar_server(request)

    with fake_client(tmp_path, "sec", FakeServer(server), clock) as client:
        fetch_filings(client, 320193)

    assert len(times) == 15
    for first, eleventh in zip(times, times[10:], strict=False):
        assert eleventh - first >= timedelta(seconds=1)


def ingest(tmp_path: Path, server: FakeServer) -> Path:
    store = tmp_path / "store"
    with fake_client(tmp_path, "sec", server, FakeClock()) as client:
        edgar.ingest(IngestContext(settings(tmp_path), client, store))
    return store


def test_ingest_sec_loads_identity_then_filings_apple_first(tmp_path: Path) -> None:
    server = FakeServer(FakeEdgar({320193: [APPLE]}))

    store = ingest(tmp_path, server)

    paths = [str(r.url.path) for r in server.requests]
    assert paths[0] == "/files/company_tickers.json"  # identity first
    assert paths[1] == "/submissions/CIK0000320193.json"  # then AAPL
    # Then every universe member and benchmark, in universes.toml's order.
    expected = [
        f"/submissions/CIK{cik:010d}.json"
        for security in universes.ingest_set()
        for cik in security.ciks
    ]
    assert paths[1:] == expected
    with PointInTimeView(utc(2020, 6, 5, 13, 30), store=store) as view:
        rows = view._select("filings", where="cik = 320193")
        assert view.resolve_ticker("AAPL").security_id == "apple"
    assert [r["accession_number"] for r in rows] == [
        "0000320193-20-000010",
        "0000320193-20-000052",
    ]  # the fiscal Q3 10-Q wasn't accepted until July 30


def test_rerunning_adds_nothing_and_makes_no_requests(tmp_path: Path) -> None:
    server = FakeServer(FakeEdgar({320193: [APPLE]}))
    store = ingest(tmp_path, server)
    requests = len(server.requests)

    ingest(tmp_path, server)

    assert len(server.requests) == requests  # answered from the raw cache
    assert len(list((store / "filings").glob("part-*.parquet"))) == 1


def test_the_vote_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    server = FakeServer(FakeEdgar({320193: [APPLE], 1418091: [TWITTER]}))

    with caplog.at_level(logging.INFO, logger="app.data.sources.edgar"):
        ingest(tmp_path, server)

    assert "apple (CIK 320193): 3 filings, 3 kept, 3 new, 0 with assumed" in caplog.text
    assert "run ahead by the Eastern offset, by a vote of 3 to 0" in caplog.text
    assert "are true UTC, by a vote of 3 to 0" in caplog.text


@pytest.mark.network
def test_live_submissions_are_read_the_way_their_file_needs(tmp_path: Path) -> None:
    # About four requests to SEC. Until late October 2026, Apple's file ran ahead by the
    # Eastern offset and Twitter's didn't; since then SEC serves both in true UTC.
    # Whichever form SEC serves, the vote must read it right.
    live = get_settings()
    if live.sec_user_agent is None:
        pytest.skip("SEC_USER_AGENT isn't set in backend/.env")

    with client_for("sec", live.model_copy(update={"data_dir": tmp_path})) as client:
        apple = fetch_filings(client, 320193)
        twitter = fetch_filings(client, 1418091)

    apple_shift, _ = runs_ahead(apple)
    twitter_shift, _ = runs_ahead(twitter)
    known = {
        r["accession_number"]: r["available_at"]
        for r in filing_rows(320193, apple, shifted=apple_shift)
        + filing_rows(1418091, twitter, shifted=twitter_shift)
    }
    assert known["0000320193-20-000052"] == utc(2020, 4, 30, 22, 3, 10)
    assert known["0000320193-20-000062"] == utc(2020, 7, 30, 23, 29, 9)
    assert known["0001193125-22-272772"] == utc(2022, 10, 29, 0, 22, 36)
