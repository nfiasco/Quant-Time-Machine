"""Universe membership: which securities were in each universe, and when (S6.5).

The curated file universes.toml lists each universe's membership spells. A security
joins on `added` and leaves on `removed`, and each date cites its source. Universe v1 is
`starter_large_caps` (decision D3, doc/data-sources.md): large US companies, each a
member from the effective date it joined the S&P 500 until the date it left, from
2010-01-01 on.

Ingestion writes the spells to the `universe_members` table. A spell is known from
00:00 ET on `added`, and its removal is a second version, known only from 00:00 ET on
`removed` (doc/time-model.md, rule 8). `PointInTimeView.universe_as_of` reads them.

The price and filing ingesters load `ingest_set()`: every member of every universe,
plus the benchmarks, such as SPY, which are loaded but never members.
"""

import logging
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, time
from itertools import pairwise
from pathlib import Path
from typing import Any

from app.data.sources.securities import CURATED, Curated, CuratedSecurity
from app.data.store import WriteResult, write_rows
from app.data.tables import UNIVERSE_MEMBERS
from app.data.timeutil import market_time

logger = logging.getLogger(__name__)

UNIVERSES_FILE = Path(__file__).with_name("universes.toml")

HISTORY_START = date(2010, 1, 1)
"""Where membership history starts (D3): the canonical backtest period's first day. A
company already in the index then is added on this date."""

PRICE_SOURCE = "tiingo"
"""The price vendor every member needs a symbol for (D2)."""

_NAME = re.compile(r"[a-z][a-z0-9_]*", re.ASCII)


@dataclass(frozen=True)
class Spell:
    """One stretch of a security's membership in a universe."""

    security: CuratedSecurity
    added: date
    """The first day it was a member."""
    source: str
    """What dates `added`."""
    removed: date | None = None
    """The first day it wasn't a member any more, or None while it still is."""
    removed_source: str | None = None
    """What dates `removed`."""


@dataclass(frozen=True)
class Universe:
    """A curated universe and its membership spells, in the file's order."""

    name: str
    spells: tuple[Spell, ...]

    @property
    def members(self) -> list[CuratedSecurity]:
        """Every security that was ever a member, in the file's order."""
        return list(
            {spell.security.id: spell.security for spell in self.spells}.values()
        )


@dataclass(frozen=True)
class Universes:
    """The curated file: each universe by name, and the benchmarks loaded with them."""

    by_name: Mapping[str, Universe]
    benchmarks: tuple[CuratedSecurity, ...]


def load_universes(
    path: Path = UNIVERSES_FILE, curated: Curated = CURATED
) -> Universes:
    """Read and check the curated universes.

    Raises ValueError for an unknown security, a member without a Tiingo symbol, a date
    without an https source, a spell before 2010-01-01 or ending before it starts,
    spells of one security that overlap, a spell starting before the security's curated
    history or while it had no ticker, or a benchmark that's also a member.
    """
    with path.open("rb") as file:
        config = tomllib.load(file)

    benchmarks = []
    for security_id in config.get("benchmarks", ()):
        if security_id not in curated.securities:
            raise ValueError(
                f"{path.name}: benchmark {security_id} isn't in securities.toml"
            )
        benchmarks.append(curated.securities[security_id])

    by_name: dict[str, Universe] = {}
    for entry in config.get("universes", ()):
        name = entry.get("name", "")
        if not _NAME.fullmatch(name):
            raise ValueError(
                f"{path.name}: {name!r} isn't a name like starter_large_caps"
            )
        if name in by_name:
            raise ValueError(f"{path.name}: {name} is listed twice")
        spells = tuple(
            _spell(item, f"{path.name}: {name}", curated)
            for item in entry.get("members", ())
        )
        _check_spells_never_overlap(spells, f"{path.name}: {name}")
        for benchmark in benchmarks:
            if any(spell.security.id == benchmark.id for spell in spells):
                raise ValueError(
                    f"{path.name}: {benchmark.id} is a benchmark, so it can't be a member "
                    f"of {name}"
                )
        by_name[name] = Universe(name, spells)
    return Universes(by_name, tuple(benchmarks))


def _spell(item: Mapping[str, Any], universe: str, curated: Curated) -> Spell:
    security_id = item.get("security", "")
    security = curated.securities.get(security_id)
    if security is None:
        raise ValueError(f"{universe}: {security_id!r} isn't in securities.toml")
    where = f"{universe}: {security_id}"
    if PRICE_SOURCE not in security.symbols:
        raise ValueError(f"{where} needs a {PRICE_SOURCE} symbol in securities.toml")

    added, removed = item.get("added"), item.get("removed")
    if type(added) is not date or added < HISTORY_START:
        raise ValueError(f"{where}: added must be a date on or after {HISTORY_START}")
    if not str(item.get("source", "")).startswith("https://"):
        raise ValueError(f"{where}: the spell from {added} needs an https source")
    if removed is not None:
        if type(removed) is not date or removed <= added:
            raise ValueError(f"{where}: removed must be a date after added, {added}")
        if not str(item.get("removed_source", "")).startswith("https://"):
            raise ValueError(f"{where}: the removal on {removed} needs an https source")
    elif "removed_source" in item:
        raise ValueError(f"{where}: removed_source needs a removed date")

    # The security's identity must resolve on the day it joins, so readers can name it.
    applying = [change for change in security.history if change.effective <= added]
    if not applying:
        raise ValueError(f"{where}: securities.toml has no history for it on {added}")
    if applying[-1].ticker is None:
        raise ValueError(f"{where}: it had no ticker on {added}")
    return Spell(
        security=security,
        added=added,
        source=item["source"],
        removed=removed,
        removed_source=item.get("removed_source"),
    )


def _check_spells_never_overlap(spells: tuple[Spell, ...], universe: str) -> None:
    """Raise ValueError if one security's spells overlap: only its last can be open."""
    by_security: dict[str, list[Spell]] = {}
    for spell in spells:
        by_security.setdefault(spell.security.id, []).append(spell)
    for security_id, own in by_security.items():
        for earlier, later in pairwise(sorted(own, key=lambda spell: spell.added)):
            if earlier.removed is None or earlier.removed > later.added:
                raise ValueError(
                    f"{universe}: {security_id}'s spells overlap on {later.added}"
                )


UNIVERSES = load_universes()
"""The curated universes and their benchmarks."""


def ingest_set(universes: Universes = UNIVERSES) -> list[CuratedSecurity]:
    """Every security the price and filing ingesters load: each universe's members, in
    the file's order, then the benchmarks."""
    loaded = {
        security.id: security
        for universe in universes.by_name.values()
        for security in universe.members
    }
    loaded.update((security.id, security) for security in universes.benchmarks)
    return list(loaded.values())


def membership_rows(universes: Universes = UNIVERSES) -> list[dict[str, object]]:
    """`universe_members` rows: each spell from 00:00 ET on `added`, and its removal as a
    second version from 00:00 ET on `removed`."""
    rows: list[dict[str, object]] = []
    for universe in universes.by_name.values():
        for spell in universe.spells:
            spell_key = {
                "universe": universe.name,
                "security_id": spell.security.id,
                "added": spell.added,
                "source": "curated",
                "time_assumed": False,
            }
            rows.append(
                spell_key
                | {
                    "removed": None,
                    "source_ref": spell.source,
                    "available_at": market_time(spell.added, time(0, 0)),
                }
            )
            if spell.removed is not None:
                rows.append(
                    spell_key
                    | {
                        "removed": spell.removed,
                        "source_ref": spell.removed_source,
                        "available_at": market_time(spell.removed, time(0, 0)),
                    }
                )
    return rows


def write_members(store: Path) -> WriteResult:
    """Write the curated membership to the `universe_members` table, skipping stored
    rows."""
    result = write_rows(store, UNIVERSE_MEMBERS, membership_rows(UNIVERSES))
    logger.info(
        "Universe membership: %d new rows, %d already stored",
        result.written,
        result.skipped,
    )
    return result
