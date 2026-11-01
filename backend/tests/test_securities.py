import logging
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.config import get_settings
from app.data.errors import NotFoundError
from app.data.http import client_for
from app.data.records import Security
from app.data.sources import IngestContext, securities
from app.data.store import write_rows
from app.data.tables import SEC_TICKERS, SECURITIES
from app.data.timeutil import parse_knowledge_time
from app.data.view import PointInTimeView
from tests.fakes import NOW, FakeClock, FakeServer, fake_client, ok, settings

CURATED = securities.CURATED


@pytest.fixture
def curated_store(store_dir: Path) -> Path:
    """A store holding the real curated file's history."""
    write_rows(store_dir, SECURITIES, securities.curated_rows(CURATED))
    return store_dir


def resolve(store: Path, ticker: str, as_of: str | datetime) -> str | None:
    """The ID of the security using `ticker` at `as_of`, or None if none did."""
    moment = parse_knowledge_time(as_of) if isinstance(as_of, str) else as_of
    with PointInTimeView(moment, store=store) as view:
        try:
            return view.resolve_ticker(ticker).security_id
        except NotFoundError:
            return None


@pytest.mark.parametrize(
    ("ticker", "as_of", "expected"),
    [
        # Facebook listed as FB on 2012-05-18 and switched to META on 2022-06-09.
        ("FB", "2012-05-17", None),
        ("FB", "2012-05-18", "meta"),
        ("FB", "2020-06-05", "meta"),
        ("META", "2020-06-05", None),
        ("FB", "2022-06-08T16:00", "meta"),
        ("FB", "2022-06-09", None),
        ("META", "2022-06-09", "meta"),
        # GOOG was Google's Class A until 2014-04-03, then its Class C; A became GOOGL.
        ("GOOG", "2010-01-04", "alphabet-a"),
        ("GOOG", "2014-04-02", "alphabet-a"),
        ("GOOG", "2014-04-03", "alphabet-c"),
        ("GOOGL", "2010-01-04", None),
        ("GOOGL", "2020-06-05", "alphabet-a"),
        # WB was Wachovia's until 2009 and unused until Weibo's IPO in 2014.
        ("WB", "2005-06-01", "wachovia"),
        ("WB", "2011-06-01", None),
        ("WB", "2020-06-05", "weibo"),
        # Twitter stopped trading on 2022-10-28.
        ("TWTR", "2022-10-27", "twitter"),
        ("TWTR", "2022-10-28", None),
        ("AAPL", "1980-12-11", None),
        ("AAPL", "2020-06-05", "apple"),
        ("aapl", "2020-06-05", "apple"),
        (" spy ", "2020-06-05", "spdr-sp500"),
    ],
)
def test_a_ticker_resolves_to_the_security_using_it_then(
    curated_store: Path, ticker: str, as_of: str, expected: str | None
) -> None:
    assert resolve(curated_store, ticker, as_of) == expected


def test_fb_in_2020_is_facebook(curated_store: Path) -> None:
    with PointInTimeView(
        parse_knowledge_time("2020-06-05"), store=curated_store
    ) as view:
        security = view.resolve_ticker("FB")

    assert security == Security(
        security_id="meta",
        ticker="FB",
        name="Facebook, Inc.",
        cik=1326801,
        share_class="Class A common stock",
        effective_date=date(2012, 5, 18),
        available_at=datetime(2012, 5, 18, 4, tzinfo=UTC),  # 00:00 EDT
        time_assumed=False,
        source="curated",
        source_ref="https://www.sec.gov/Archives/edgar/data/1326801/000119312512240111/0001193125-12-240111-index.htm",
    )


@pytest.mark.parametrize(
    ("ticker", "as_of", "name", "cik"),
    [
        ("AAPL", "2005-01-03", "Apple Computer, Inc.", 320193),
        ("AAPL", "2007-01-09", "Apple Inc.", 320193),
        ("FB", "2021-10-28", "Meta Platforms, Inc.", 1326801),
        ("GOOGL", "2015-10-01", "Google Inc.", 1288776),
        ("GOOGL", "2015-10-02", "Alphabet Inc.", 1652044),
        ("JPM", "2003-01-02", "J.P. Morgan Chase & Co.", 19617),
        ("JPM", "2020-06-05", "JPMorgan Chase & Co.", 19617),
    ],
)
def test_names_and_ciks_follow_the_history(
    curated_store: Path, ticker: str, as_of: str, name: str, cik: int
) -> None:
    with PointInTimeView(parse_knowledge_time(as_of), store=curated_store) as view:
        security = view.resolve_ticker(ticker)

    assert (security.name, security.cik) == (name, cik)


def snapshot(store: Path, fetched_at: datetime, *listed: tuple[int, str, str]) -> None:
    """Store one download of SEC's ticker file listing `listed`."""
    write_rows(
        store,
        SEC_TICKERS,
        [
            {
                "cik": cik,
                "ticker": ticker,
                "name": name,
                "source": "edgar",
                "source_ref": f"test snapshot {fetched_at.isoformat()}",
                "available_at": fetched_at,
                "time_assumed": True,
            }
            for cik, ticker, name in listed
        ],
    )


OCTOBER = datetime(2026, 10, 1, 12, tzinfo=UTC)
NOVEMBER = datetime(2026, 11, 2, 12, tzinfo=UTC)


def test_a_ticker_only_sec_lists_resolves_from_the_download(
    curated_store: Path,
) -> None:
    snapshot(curated_store, OCTOBER, (1045810, "NVDA", "NVIDIA CORP"))

    assert resolve(curated_store, "NVDA", OCTOBER.replace(hour=11)) is None
    with PointInTimeView(OCTOBER, store=curated_store) as view:
        security = view.resolve_ticker("nvda")

    assert security.security_id == "1045810-NVDA"
    assert (security.name, security.cik) == ("NVIDIA CORP", 1045810)
    assert (security.share_class, security.effective_date) == (None, None)
    assert security.available_at == OCTOBER
    assert security.time_assumed is True


def test_only_the_newest_download_counts(curated_store: Path) -> None:
    # A ticker that left SEC's file stops resolving once a newer download is known.
    snapshot(curated_store, OCTOBER, (1045810, "NVDA", "NVIDIA"), (1, "OLD", "Old Co"))
    snapshot(curated_store, NOVEMBER, (1045810, "NVDA", "NVIDIA"))

    assert resolve(curated_store, "OLD", "2026-10-15") == "1-OLD"
    assert resolve(curated_store, "OLD", NOVEMBER) is None
    assert resolve(curated_store, "NVDA", NOVEMBER) == "1045810-NVDA"


def test_the_curated_history_comes_before_sec(curated_store: Path) -> None:
    # Even if SEC's file listed Weibo under WB in 2005, 2005's WB was Wachovia.
    snapshot(curated_store, datetime(2005, 1, 3, tzinfo=UTC), (1595761, "WB", "Weibo"))

    assert resolve(curated_store, "WB", "2005-06-01") == "wachovia"


def test_a_ticker_listed_under_two_companies_is_not_resolved(
    curated_store: Path,
) -> None:
    snapshot(curated_store, OCTOBER, (1, "TWIN", "One Co"), (2, "TWIN", "Two Co"))

    assert resolve(curated_store, "TWIN", NOVEMBER) is None


def test_the_securities_fixture_matches_the_curated_file(fixture_store: Path) -> None:
    # tests/fixtures/securities.csv copies the whole curated history of each security
    # it lists, the M2 ticker set among them, plus a canary.
    def facts(rows: list[dict[str, object]]) -> list[tuple[object, ...]]:
        columns = ("security_id", "effective_date", "ticker", "name", "cik")
        more = ("share_class", "source_ref", "available_at", "time_assumed")
        return sorted(tuple(row[c] for c in (*columns, *more)) for row in rows)

    with PointInTimeView(datetime(2098, 1, 1, tzinfo=UTC), store=fixture_store) as view:
        stored = view._select("securities")
    listed = {row["security_id"] for row in stored}
    curated = [
        r for r in securities.curated_rows(CURATED) if r["security_id"] in listed
    ]

    assert facts(stored) == facts(curated)
    assert {s.id for s in CURATED.m2_ticker_set} <= listed


def test_the_m2_ticker_set_is_the_test_set() -> None:
    starter = CURATED.m2_ticker_set

    assert [s.id for s in starter] == [
        "apple",
        "microsoft",
        "jpmorgan",
        "meta",
        "twitter",
        "spdr-sp500",
    ]
    assert [s.symbols["tiingo"] for s in starter] == [
        "AAPL",
        "MSFT",
        "JPM",
        "META",
        "TWTR",
        "SPY",
    ]
    assert [s.ciks for s in starter] == [
        [320193],
        [789019],
        [19617],
        [1326801],
        [1418091],
        [884394],
    ]


def test_alphabets_shares_had_two_ciks() -> None:
    assert CURATED.securities["alphabet-a"].ciks == [1288776, 1652044]


ONE = """
[[securities]]
id = "one"
share_class = "Common stock"

[[securities.history]]
from = 2000-01-03
ticker = "ONE"
name = "One Inc."
source = "https://example.com/one"
"""

EARLIER = """
[[securities.history]]
from = 1999-01-04
ticker = "ONE"
source = "https://example.com/earlier"
"""


@pytest.mark.parametrize(
    ("toml", "problem"),
    [
        (ONE.replace('id = "one"', 'id = "One!"'), "isn't an ID"),
        (
            ONE.replace('source = "https://example.com/one"', ""),
            "needs an https source",
        ),
        (ONE.replace('ticker = "ONE"', ""), "needs a ticker or delisted"),
        (ONE.replace('ticker = "ONE"', 'ticker = "one"'), "isn't an uppercase ticker"),
        (ONE.replace('name = "One Inc."', ""), "first entry needs a name"),
        (ONE.replace('share_class = "Common stock"', ""), "needs a share_class"),
        (ONE + EARLIER, "history dates must increase"),
        (ONE + ONE, "one is listed twice"),
        (ONE + ONE.replace('id = "one"', 'id = "two"'), "one and two both use ONE"),
        ('m2_ticker_set = ["nope"]\n' + ONE, "M2 ticker set names unknown nope"),
    ],
)
def test_the_curated_file_is_checked(tmp_path: Path, toml: str, problem: str) -> None:
    path = tmp_path / "securities.toml"
    path.write_text(toml, encoding="utf-8")

    with pytest.raises(ValueError, match=problem):
        securities.load_curated(path)


GONE = """
[[securities.history]]
from = 2001-01-02
delisted = true
source = "https://example.com/gone"
"""


def test_a_ticker_can_change_hands_after_a_gap(tmp_path: Path) -> None:
    later = ONE.replace('id = "one"', 'id = "two"').replace("2000-01-03", "2002-01-02")
    path = tmp_path / "securities.toml"
    path.write_text(ONE + GONE + later, encoding="utf-8")

    assert set(securities.load_curated(path).securities) == {"one", "two"}


def sec_listing(*extra: tuple[int, str, str], drop: str = "") -> dict[str, object]:
    """A ticker file listing every curated security's current ticker, plus `extra`."""
    listed = [
        (
            security.history[-1].cik,
            security.history[-1].ticker,
            security.history[-1].name,
        )
        for security in CURATED.securities.values()
        if security.history[-1].ticker not in (None, drop)
    ]
    return {
        str(n): {"cik_str": cik, "ticker": ticker, "title": name}
        for n, (cik, ticker, name) in enumerate([*listed, *extra])
    }


def ingest(tmp_path: Path, server: FakeServer) -> Path:
    store = tmp_path / "store"
    with fake_client(tmp_path, "sec", server, FakeClock()) as client:
        securities.ingest(IngestContext(settings(tmp_path), client, store))
    return store


def test_ingest_loads_the_curated_history_and_a_snapshot(tmp_path: Path) -> None:
    server = FakeServer(ok(sec_listing((1045810, "NVDA", "NVIDIA CORP"))))

    store = ingest(tmp_path, server)

    assert str(server.requests[0].url) == securities.TICKER_FILE
    assert resolve(store, "FB", "2020-06-05") == "meta"
    with PointInTimeView(NOW, store=store) as view:
        nvda = view.resolve_ticker("NVDA")
    assert nvda.security_id == "1045810-NVDA"
    assert (nvda.available_at, nvda.time_assumed, nvda.source) == (NOW, True, "edgar")
    assert nvda.source_ref == f"{securities.TICKER_FILE} fetched 2026-10-19T12:00:00Z"


def test_rerunning_adds_nothing_and_makes_no_requests(tmp_path: Path) -> None:
    server = FakeServer(ok(sec_listing()))
    store = ingest(tmp_path, server)

    ingest(tmp_path, server)

    assert len(server.requests) == 1  # answered from the raw cache
    for table in ("securities", "sec_tickers"):
        assert len(list((store / table).glob("part-*.parquet"))) == 1


def test_a_curated_ticker_missing_from_sec_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server = FakeServer(ok(sec_listing(drop="META")))

    with caplog.at_level(logging.WARNING, logger="app.data.sources.securities"):
        ingest(tmp_path, server)

    assert (
        "meta: securities.toml says it trades as META under CIK 1326801" in caplog.text
    )
    # Delisted securities aren't expected in SEC's file.
    assert "twitter" not in caplog.text
    assert "wachovia" not in caplog.text


@pytest.mark.network
def test_live_ticker_file_lists_the_curated_tickers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # One request to SEC: checks every curated security's current ticker and CIK.
    live = get_settings()
    if live.sec_user_agent is None:
        pytest.skip("SEC_USER_AGENT isn't set in backend/.env")

    with client_for("sec", live.model_copy(update={"data_dir": tmp_path})) as client:
        rows = securities.ticker_file_rows(client.get(securities.TICKER_FILE))
    with caplog.at_level(logging.WARNING, logger="app.data.sources.securities"):
        securities.check_against_sec(CURATED, rows)

    assert caplog.text == ""
    assert len(rows) > 5000
