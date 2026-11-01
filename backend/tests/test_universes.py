import csv
import io
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from app.data import calendar
from app.data.errors import NotFoundError
from app.data.records import UniverseMember
from app.data.sources import securities, universes
from app.data.sources.universes import load_universes
from app.data.store import write_rows
from app.data.tables import SECURITIES, UNIVERSE_MEMBERS
from app.data.timeutil import parse_knowledge_time
from app.data.view import PointInTimeView

V1 = "starter_large_caps"
CURATED = securities.CURATED
FACEBOOK_JOINS = (
    "https://press.spglobal.com/2013-12-11-Facebook-Set-to-Join-the-S-P-100-500-Alliance"
    "-Data-Systems-and-Mohawk-to-Join-the-S-P-500-Changes-to-the-S-P-MidCap-400-and-the"
    "-S-P-SmallCap-600"
)


def members(store: Path, as_of: str) -> dict[str, str | None]:
    """Each member of universe v1 at `as_of`, with its ticker then."""
    with PointInTimeView(parse_knowledge_time(as_of), store=store) as view:
        return {m.security_id: m.ticker for m in view.universe_as_of(V1)}


def test_universe_change_applies_from_effective_date(fixture_store: Path) -> None:
    # S&P announced on November 16, 2020 that Tesla would join the S&P 500 before the
    # open on Monday, December 21 (doc/time-model.md, rule 8).
    assert "tesla" not in members(fixture_store, "2020-12-01")
    assert "tesla" not in members(fixture_store, "2020-12-18")
    assert members(fixture_store, "2020-12-21")["tesla"] == "TSLA"
    assert members(fixture_store, "2021-01-04")["tesla"] == "TSLA"


def test_a_company_that_left_is_a_member_until_its_removal(fixture_store: Path) -> None:
    # Twitter joined on 2018-06-07, stopped trading on 2022-10-28 when its buyout
    # closed, and left the S&P 500 on 2022-11-01.
    assert "twitter" not in members(fixture_store, "2018-06-06")
    assert members(fixture_store, "2018-06-07")["twitter"] == "TWTR"
    assert members(fixture_store, "2022-10-27")["twitter"] == "TWTR"
    assert members(fixture_store, "2022-10-31")["twitter"] is None  # no ticker then
    assert "twitter" not in members(fixture_store, "2022-11-01")


def test_a_removal_is_invisible_before_it_happens(fixture_store: Path) -> None:
    with PointInTimeView(
        parse_knowledge_time("2020-06-05"), store=fixture_store
    ) as view:
        rows = view._select("universe_members", where="security_id = 'twitter'")

    assert [(r["added"], r["removed"]) for r in rows] == [(date(2018, 6, 7), None)]


def test_members_come_with_their_identity_then(fixture_store: Path) -> None:
    with PointInTimeView(
        parse_knowledge_time("2020-06-05"), store=fixture_store
    ) as view:
        [meta] = [m for m in view.universe_as_of(V1) if m.security_id == "meta"]

    assert meta == UniverseMember(
        universe=V1,
        security_id="meta",
        ticker="FB",
        name="Facebook, Inc.",
        cik=1326801,
        added=date(2013, 12, 23),
        available_at=datetime(2013, 12, 23, 5, tzinfo=UTC),  # 00:00 EST
        time_assumed=False,
        source="curated",
        source_ref=FACEBOOK_JOINS,
    )


def test_the_universe_is_empty_before_2010(fixture_store: Path) -> None:
    assert members(fixture_store, "2009-12-31") == {}
    assert members(fixture_store, "2010-01-04") == {"apple": "AAPL"}


def test_an_unknown_universe_is_not_found(fixture_store: Path) -> None:
    with (
        PointInTimeView(
            parse_knowledge_time("2020-06-05"), store=fixture_store
        ) as view,
        pytest.raises(NotFoundError),
    ):
        view.universe_as_of("sp500")


def test_universe_names_match_in_any_case(fixture_store: Path) -> None:
    with PointInTimeView(
        parse_knowledge_time("2020-06-05"), store=fixture_store
    ) as view:
        assert view.universe_as_of(" Starter_Large_Caps ") == view.universe_as_of(V1)


def test_a_removal_is_a_second_version_of_its_spell() -> None:
    rows = [r for r in universes.membership_rows() if r["security_id"] == "twitter"]

    assert [(r["added"], r["removed"], r["available_at"]) for r in rows] == [
        (date(2018, 6, 7), None, datetime(2018, 6, 7, 4, tzinfo=UTC)),
        (date(2018, 6, 7), date(2022, 11, 1), datetime(2022, 11, 1, 4, tzinfo=UTC)),
    ]


def test_the_membership_fixture_matches_the_curated_file(fixture_store: Path) -> None:
    # tests/fixtures/universe_members.csv copies the curated rows of the spells it
    # lists, plus a canary.
    def facts(rows: list[dict[str, object]]) -> list[tuple[object, ...]]:
        columns = ("universe", "security_id", "added", "removed", "source_ref")
        more = ("available_at", "time_assumed")
        # Sorted by their text, since `removed` mixes dates and None.
        return sorted(
            (tuple(row[c] for c in (*columns, *more)) for row in rows), key=str
        )

    with PointInTimeView(datetime(2098, 1, 1, tzinfo=UTC), store=fixture_store) as view:
        stored = view._select("universe_members")
    spells = {(r["universe"], r["security_id"], r["added"]) for r in stored}
    curated = [
        r
        for r in universes.membership_rows()
        if (r["universe"], r["security_id"], r["added"]) in spells
    ]

    assert facts(stored) == facts(curated)


def test_v1_follows_d3() -> None:
    # doc/data-sources.md: 50 to 100 large US companies, at least 10 of which joined
    # after 2010-01-01, Tesla and Meta among them, and at least 10 left, Twitter among
    # them, with at least two banks.
    v1 = universes.UNIVERSES.by_name[V1]
    joined = {s.security.id for s in v1.spells if s.added > universes.HISTORY_START}
    left = {s.security.id for s in v1.spells if s.removed is not None}

    assert 50 <= len(v1.members) <= 100
    assert len(joined) >= 10 and {"tesla", "meta"} <= joined
    assert len(left) >= 10 and "twitter" in left
    assert {"jpmorgan", "bank-of-america"} <= {s.id for s in v1.members}
    assert all(s.removed is None or s.removed.year <= 2025 for s in v1.spells)


def test_ingesters_load_every_member_then_spy() -> None:
    loaded = universes.ingest_set()

    assert loaded == [
        *universes.UNIVERSES.by_name[V1].members,
        CURATED.securities["spdr-sp500"],
    ]
    assert loaded[0].id == "apple"


SPELL = """
[[universes]]
name = "starter_large_caps"

[[universes.members]]
security = "apple"
added = 2010-01-01
source = "https://example.com/apple"
"""

REMOVED = """removed = 2013-09-23
removed_source = "https://example.com/out"
"""

REJOINED = """
[[universes.members]]
security = "apple"
added = 2017-03-20
source = "https://example.com/back"
"""


def test_a_company_that_rejoined_has_two_spells(
    tmp_path: Path, store_dir: Path
) -> None:
    path = tmp_path / "universes.toml"
    path.write_text(SPELL + REMOVED + REJOINED, encoding="utf-8")
    rejoined = load_universes(path)
    write_rows(store_dir, SECURITIES, securities.curated_rows(CURATED))
    write_rows(store_dir, UNIVERSE_MEMBERS, universes.membership_rows(rejoined))

    assert members(store_dir, "2012-06-01") == {"apple": "AAPL"}
    assert members(store_dir, "2015-06-01") == {}
    assert members(store_dir, "2018-06-01") == {"apple": "AAPL"}


@pytest.mark.parametrize(
    ("toml", "problem"),
    [
        (SPELL.replace('"apple"', '"nope"'), "'nope' isn't in securities.toml"),
        (SPELL.replace('"apple"', '"wachovia"'), "needs a tiingo symbol"),
        (SPELL.replace("2010-01-01", "2009-12-31"), "on or after 2010-01-01"),
        (SPELL.replace('source = "https://example.com/apple"', ""), "https source"),
        (SPELL + REMOVED.replace("2013-09-23", "2009-06-01"), "a date after added"),
        (SPELL + "removed = 2013-09-23\n", "removal on 2013-09-23 needs an https"),
        (SPELL + 'removed_source = "https://example.com/out"\n', "needs a removed"),
        (SPELL + REJOINED, "apple's spells overlap on 2017-03-20"),
        (SPELL.replace("starter_large_caps", "Starter Large Caps"), "isn't a name"),
        (SPELL + SPELL, "starter_large_caps is listed twice"),
        ('benchmarks = ["nope"]\n' + SPELL, "benchmark nope isn't in securities.toml"),
        ('benchmarks = ["apple"]\n' + SPELL, "apple is a benchmark"),
        # Tesla's history starts at its IPO on 2010-06-29.
        (SPELL.replace('"apple"', '"tesla"'), "no history for it on 2010-01-01"),
        # Twitter stopped trading on 2022-10-28.
        (
            SPELL.replace('"apple"', '"twitter"').replace("2010-01-01", "2023-01-03"),
            "had no ticker on 2023-01-03",
        ),
    ],
)
def test_the_curated_universes_are_checked(
    tmp_path: Path, toml: str, problem: str
) -> None:
    path = tmp_path / "universes.toml"
    path.write_text(toml, encoding="utf-8")

    with pytest.raises(ValueError, match=problem):
        load_universes(path)


@pytest.mark.network
def test_live_tiingo_covers_every_members_spell() -> None:
    # One download of Tiingo's public ticker list, which needs no key and counts against
    # no limit. Tiingo answers a symbol with its latest listing, so that listing must
    # cover the whole spell: a reused symbol, such as Monsanto's MON, which a SPAC took
    # in 2021, fails. A spell ends when the security left or stopped trading.
    response = httpx2.get(
        "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip",
        timeout=120,
    )
    response.raise_for_status()
    with (
        zipfile.ZipFile(io.BytesIO(response.content)) as archive,
        archive.open(archive.namelist()[0]) as listing,
    ):
        rows = list(csv.DictReader(io.TextIOWrapper(listing, encoding="utf-8")))
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        symbol = row["ticker"].upper()
        if row["startDate"] >= latest.get(symbol, {}).get("startDate", ""):
            latest[symbol] = row
    recently = (datetime.now(UTC) - timedelta(days=7)).date().isoformat()

    gaps = []
    for spell in universes.UNIVERSES.by_name[V1].spells:
        symbol = spell.security.symbols["tiingo"]
        stopped = [
            change.effective
            for change in spell.security.history
            if change.ticker is None and change.effective > spell.added
        ]
        ends = [day for day in (spell.removed, *stopped) if day is not None]
        needed = calendar.previous_session(min(ends)).isoformat() if ends else recently
        row = latest.get(symbol, {"startDate": "9999", "endDate": ""})
        if row["startDate"] > spell.added.isoformat() or row["endDate"] < needed:
            gaps.append(
                f"{spell.security.id} ({symbol}): {row['startDate']} to "
                f"{row['endDate']}, needed {spell.added} to {needed}"
            )

    assert gaps == []
