import logging
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from app.config import get_settings
from app.data.http import RateLimitExceeded, client_for
from app.data.sources import IngestContext, tiingo, universes
from app.data.sources.prices import SourceBar, ingest_prices, last_settled_session
from app.data.sources.securities import CURATED
from app.data.sources.tiingo import TiingoPriceSource
from app.data.store import write_rows
from app.data.tables import PRICE_BARS
from app.data.view import PointInTimeView
from tests.fakes import FakeClock, FakeServer, fake_client, ok, settings

APPLE = CURATED.securities["apple"]
TWITTER = CURATED.securities["twitter"]
LOGGER = "app.data.sources.prices"


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def bar(
    day: str, close: float = 100.0, *, dividend: float = 0.0, split: float = 1.0
) -> SourceBar:
    """A made-up raw bar (Tiingo's terms don't allow sharing its data)."""
    return SourceBar(
        session_date=date.fromisoformat(day),
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=1_000_000,
        dividend=dividend,
        split_factor=split,
    )


class FakeSource:
    """A PriceSource serving made-up bars, which records each request."""

    name = "tiingo"
    settled_by = time(20, 0)

    def __init__(self, *bars: SourceBar) -> None:
        self.bars = bars
        self.requests: list[tuple[str, date, date]] = []

    def fetch_bars(self, symbol: str, start: date, end: date) -> list[SourceBar]:
        self.requests.append((symbol, start, end))
        return [b for b in self.bars if start <= b.session_date <= end]


def stored(store: Path, table: str = "price_bars") -> list[dict[str, object]]:
    with PointInTimeView(utc(2098, 1, 1), store=store) as view:
        return view._select(table)


def test_early_close_bar_known_at_1300(store_dir: Path) -> None:
    # The NYSE closed at 13:00 ET on Friday, November 27, 2020, after Thanksgiving.
    source = FakeSource(bar("2020-11-25"), bar("2020-11-27"))

    ingest_prices(
        store_dir,
        source,
        [APPLE],
        now=utc(2020, 11, 28, 12),
        history_start=date(2020, 11, 23),
    )

    assert {r["session_date"]: r["available_at"] for r in stored(store_dir)} == {
        date(2020, 11, 25): utc(2020, 11, 25, 21),  # 16:00 EST
        date(2020, 11, 27): utc(2020, 11, 27, 18),  # 13:00 EST
    }


def test_a_bar_is_stored_with_its_provenance(store_dir: Path) -> None:
    ingest_prices(
        store_dir,
        FakeSource(bar("2020-06-04", 102.0)),
        [APPLE],
        now=utc(2020, 6, 5, 12),
        history_start=date(2020, 6, 4),
    )

    [row] = stored(store_dir)
    assert {k: v for k, v in row.items() if k != "ingested_at"} == {
        "security_id": "apple",
        "session_date": date(2020, 6, 4),
        "open": 101.0,
        "high": 103.0,
        "low": 100.0,
        "close": 102.0,
        "volume": 1_000_000,
        "source": "tiingo",
        "source_ref": "tiingo AAPL 2020-06-04",
        "available_at": utc(2020, 6, 4, 20),
        "time_assumed": False,
    }


def test_splits_and_dividends_are_stored_as_reported(store_dir: Path) -> None:
    source = FakeSource(
        bar("2014-06-05", dividend=3.29),
        bar("2014-06-06"),
        # Tiingo reports Apple's 7-for-1 split as 7.000007; S6.4 rounds it, not ingest.
        bar("2014-06-09", split=7.000007),
    )

    [result] = ingest_prices(
        store_dir,
        source,
        [APPLE],
        now=utc(2014, 6, 10, 12),
        history_start=date(2014, 6, 5),
    )

    assert result.actions == 2
    assert [
        (r["ex_date"], r["action"], r["value"], r["available_at"])
        for r in stored(store_dir, "corporate_actions")
    ] == [
        (date(2014, 6, 5), "dividend", 3.29, utc(2014, 6, 5, 20)),
        (date(2014, 6, 9), "split", 7.000007, utc(2014, 6, 9, 20)),
    ]


def test_missing_sessions_are_reported(
    store_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = FakeSource(*(bar(f"2020-06-0{day}") for day in (1, 2, 4, 5)))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        [result] = ingest_prices(
            store_dir,
            source,
            [APPLE],
            now=utc(2020, 6, 6, 12),
            history_start=date(2020, 6, 1),
        )

    assert result.missing_sessions == (date(2020, 6, 3),)
    assert "apple: no bar for these sessions: 2020-06-03" in caplog.text


def test_later_runs_fetch_only_new_bars(store_dir: Path) -> None:
    source = FakeSource(*(bar(f"2020-06-0{day}") for day in range(1, 6)))

    def run(now: datetime) -> list:
        return ingest_prices(
            store_dir, source, [APPLE], now=now, history_start=date(2020, 6, 1)
        )

    # Friday, June 5, 2020, at 18:00 ET: that day's bars settle at 20:00, so the
    # first run stops at June 4.
    run(utc(2020, 6, 5, 22))
    # At 21:00 ET, only June 5 is new.
    run(utc(2020, 6, 6, 1))
    # Up to date: no request at all.
    [result] = run(utc(2020, 6, 6, 2))

    assert source.requests == [
        ("AAPL", date(2020, 6, 1), date(2020, 6, 4)),
        ("AAPL", date(2020, 6, 5), date(2020, 6, 5)),
    ]
    assert result.window is None
    assert result.note == "up to date through 2020-06-05"
    assert len(stored(store_dir)) == 5


def test_bars_on_days_without_a_session_are_dropped(
    store_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The NYSE was closed on Friday, July 3, 2020, for Independence Day.
    source = FakeSource(bar("2020-07-02"), bar("2020-07-03"), bar("2020-07-06"))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        [result] = ingest_prices(
            store_dir,
            source,
            [APPLE],
            now=utc(2020, 7, 7, 12),
            history_start=date(2020, 7, 1),
        )

    assert [r["session_date"] for r in stored(store_dir)] == [
        date(2020, 7, 2),
        date(2020, 7, 6),
    ]
    assert "apple: dropped 1 bars" in caplog.text
    assert "such as 2020-07-03" in caplog.text
    assert result.missing_sessions == ()


def price_row(security_id: str, day: date) -> dict[str, object]:
    return {
        "security_id": security_id,
        "session_date": day,
        "open": 50.0,
        "high": 51.0,
        "low": 49.0,
        "close": 50.5,
        "volume": 1000,
        "source": "tiingo",
        "source_ref": f"made up: {security_id} {day}",
        "available_at": utc(day.year, day.month, day.day, 20),
        "time_assumed": False,
    }


def test_a_delisted_security_is_not_asked_again(store_dir: Path) -> None:
    # Twitter's last session was October 27, 2022; it stopped trading the next day.
    write_rows(store_dir, PRICE_BARS, [price_row("twitter", date(2022, 10, 27))])
    source = FakeSource()

    [result] = ingest_prices(store_dir, source, [TWITTER], now=utc(2026, 10, 22, 12))

    assert source.requests == []
    assert result.note == "delisted on 2022-10-28"


def test_a_delisted_securitys_history_is_loaded_once(store_dir: Path) -> None:
    source = FakeSource(bar("2022-10-27"))

    ingest_prices(store_dir, source, [TWITTER], now=utc(2026, 10, 22, 12))

    [(symbol, start, _)] = source.requests
    assert (symbol, start) == ("TWTR", date(2005, 1, 1))


def test_a_security_without_a_symbol_is_skipped(store_dir: Path) -> None:
    source = FakeSource(bar("2020-06-04"))

    [result] = ingest_prices(
        store_dir, source, [replace(APPLE, symbols={})], now=utc(2020, 6, 5, 12)
    )

    assert source.requests == []
    assert result.note == "no tiingo symbol"


@pytest.mark.parametrize(
    ("now", "settled"),
    [
        (utc(2020, 6, 5, 23, 59), date(2020, 6, 4)),  # Friday, 19:59 EDT
        (utc(2020, 6, 6), date(2020, 6, 5)),  # Friday, 20:00 EDT
        (utc(2020, 6, 6, 16), date(2020, 6, 5)),  # Saturday
        (utc(2020, 6, 8, 13, 30), date(2020, 6, 5)),  # Monday, 09:30 EDT
        (utc(2020, 7, 3, 23), date(2020, 7, 2)),  # Independence Day, observed
        (utc(2020, 11, 28, 1), date(2020, 11, 27)),  # 20:00 EST after an early close
    ],
)
def test_the_range_ends_at_the_last_settled_session(
    now: datetime, settled: date
) -> None:
    assert last_settled_session(now, time(20, 0)) == settled


def tiingo_record(day: str, close: float) -> dict[str, object]:
    """A made-up bar in Tiingo's format, adjusted fields included."""
    return {
        "date": f"{day}T00:00:00.000Z",
        "open": close,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": 1000,
        "adjOpen": close / 28,
        "adjHigh": (close + 2) / 28,
        "adjLow": (close - 2) / 28,
        "adjClose": close / 28,
        "adjVolume": 28000,
        "divCash": 0.0,
        "splitFactor": 1.0,
    }


def test_tiingo_bars_keep_their_raw_prices(tmp_path: Path) -> None:
    # Made up: a raw close of 500 that later splits would adjust to about 17.86.
    server = FakeServer(ok([tiingo_record("2012-09-19", 500.0)]))

    with fake_client(tmp_path, "tiingo", server, FakeClock()) as client:
        bars = TiingoPriceSource(client).fetch_bars(
            "AAPL", date(2012, 9, 19), date(2012, 9, 19)
        )

    request = server.requests[0]
    assert request.url.path == "/tiingo/daily/AAPL/prices"
    assert dict(request.url.params) == {
        "startDate": "2012-09-19",
        "endDate": "2012-09-19",
    }
    assert bars == [
        SourceBar(date(2012, 9, 19), 500.0, 502.0, 498.0, 500.0, 1000, 0.0, 1.0)
    ]


def test_ingest_tiingo_loads_the_universe_and_spy(tmp_path: Path) -> None:
    # One made-up bar for every symbol. With more than 50 securities, a first load
    # stops at Tiingo's hourly limit, and a run an hour later picks up where it stopped.
    server = FakeServer(lambda request: ok([tiingo_record("2020-06-04", 100.0)]))
    store = tmp_path / "store"
    clock = FakeClock()

    def run() -> None:
        with fake_client(tmp_path, "tiingo", server, clock) as client:
            context = IngestContext(settings(tmp_path), client, store)
            tiingo.ingest(context, now=utc(2020, 6, 5, 12))

    for _ in range(3):
        try:
            run()
            break
        except RateLimitExceeded:
            clock.now += timedelta(hours=1)
    else:
        pytest.fail("the universe never finished loading")
    run()  # up to date: no requests

    symbols = [request.url.path.split("/")[3] for request in server.requests]
    expected = [security.symbols["tiingo"] for security in universes.ingest_set()]
    assert symbols == expected  # each once, in universes.toml's order
    assert symbols[0] == "AAPL" and symbols[-1] == "SPY"
    assert len(stored(store)) == len(expected)
    # Identity and membership come along, so prices can be read by ticker at once.
    with PointInTimeView(utc(2020, 6, 5, 13, 30), store=store) as view:
        assert view.resolve_ticker("FB").security_id == "meta"
        members = {m.security_id for m in view.universe_as_of("starter_large_caps")}
    assert {"apple", "meta"} <= members
    assert "tesla" not in members  # it joined on 2020-12-21


@pytest.mark.network
def test_live_tiingo_bars_are_raw_with_the_split_factor_as_given(
    tmp_path: Path,
) -> None:
    # One request: Apple's last session before its 7-for-1 split and its first after.
    live = get_settings()
    if live.tiingo_api_key is None:
        pytest.skip("TIINGO_API_KEY isn't set in backend/.env")

    with client_for("tiingo", live.model_copy(update={"data_dir": tmp_path})) as client:
        bars = TiingoPriceSource(client).fetch_bars(
            "AAPL", date(2014, 6, 6), date(2014, 6, 9)
        )

    before, after = bars
    assert (before.session_date, after.session_date) == (
        date(2014, 6, 6),
        date(2014, 6, 9),
    )
    assert before.close is not None and before.close > 600  # raw, not split-adjusted
    assert after.close is not None and after.close < 100
    assert after.split_factor == 7.000007  # as Tiingo reports it; S6.4 rounds it
