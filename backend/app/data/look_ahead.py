"""Look-ahead: what wasn't public yet at a knowledge time, but is in our data (S8.3).

THIS MODULE DELIBERATELY LOOKS AHEAD. It exists only to teach: the "not yet known" half
of GET /v1/snapshot shows what a decision at the knowledge time must never see, such as
that day's close, the next 10-Q, and later revisions of a value. Nothing that makes or
tests decisions may use it. tests/test_look_ahead.py fails if any module in
app/backtest/ imports it, directly or through another module, and if anything but the
snapshot route (app/api/snapshot.py) does. Keep the MCP tools (E10) away from it too.

It still reads through `PointInTimeView`, never the store itself. Its view is pinned to
the same data version as the request's view, and bound to the moment that version was
cut: its manifest's `ingested_through`. So "not yet known" means public after the
knowledge time, and by the time our data was cut. A data version's answers never change,
and a row dated later, such as the test fixtures' 2099 canaries, never shows.

Every read asks for rows public after the knowledge time, through the view's internal
reads (`_select` and `_ciks`). That's on purpose: "what came after T?" is the one
question the view's public reads must never answer.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from app.config import get_settings
from app.data import fundamentals, versions
from app.data.records import (
    Filing,
    Fundamental,
    MacroObservation,
    NextBar,
    Security,
    UniverseChange,
)
from app.data.sources import metrics
from app.data.sources.edgar import FORM_FAMILIES
from app.data.store import store_dir
from app.data.timeutil import to_utc
from app.data.view import PointInTimeView, _filing, _fundamental


class LookAhead:
    """What became public after `knowledge_time`, up to the data version's cut.

    Each read takes the `Security` a `PointInTimeView` at the knowledge time resolved,
    so that FB in 2020 reads Facebook's later filings, and every record it returns has
    `knowledge_time < available_at <= horizon`. Close it when done, like a view:

        with LookAhead(view.knowledge_time, data_version=view.data_version) as ahead:
            ahead.next_filings(view.resolve_ticker("AAPL"))["10-Q"]  # accepted July 30
    """

    def __init__(
        self,
        knowledge_time: datetime,
        *,
        data_version: str | None = None,
        store: Path | None = None,
    ) -> None:
        """Look past an aware `knowledge_time`, through `data_version`'s data.

        `store` defaults to DATA_DIR/store. Without a data version, which only a store
        that no ingestion run has finished in lacks, the horizon is now. Raises
        DataVersionError as `PointInTimeView` does.
        """
        self.knowledge_time = to_utc(knowledge_time)
        if store is None:
            store = store_dir(get_settings().data_dir)
        # When the data version was cut: nothing that became public later is read.
        self.horizon = (
            datetime.now(UTC)
            if data_version is None
            else versions.read_manifest(store, data_version).ingested_through
        )
        self._view = PointInTimeView(
            self.horizon, data_version=data_version, store=store
        )

    def next_bar(self, security: Security) -> NextBar | None:
        """When the security's first bar after the knowledge time became known, without
        its prices. At 09:30 ET on June 5, 2020, that's June 5's, known at 16:00. None
        if our data has no later bar, as after a security's last session."""
        rows = self._view._select(
            "price_bars",
            where="security_id = ? AND available_at > ?",
            params=[security.security_id, self.knowledge_time],
            order_by="available_at, session_date",
            limit=1,
        )
        if not rows:
            return None
        return NextBar(rows[0]["session_date"], rows[0]["available_at"])

    def next_filings(self, security: Security) -> dict[str, Filing | None]:
        """The first original 10-K, 10-Q, and 8-K EDGAR accepted after the knowledge
        time, by form family, each None if our data has none. At 09:30 ET on June 5,
        2020, Apple's next 10-Q is the one for the quarter ended June 27, accepted on
        July 30. The filings of every CIK the security has had are searched."""
        found: dict[str, Filing | None] = dict.fromkeys(FORM_FAMILIES)
        ciks = self._view._ciks(security.security_id, security.cik)
        if not ciks:
            return found
        for family, forms in FORM_FAMILIES.items():
            rows = self._view._select(
                "filings",
                where=(
                    f"cik IN ({', '.join('?' * len(ciks))}) "
                    f"AND form IN ({', '.join('?' * len(forms))}) AND available_at > ?"
                ),
                params=[*ciks, *forms, self.knowledge_time],
                latest_per_key=True,
                order_by="available_at, accession_number",
                limit=1,
            )
            found[family] = _filing(security, rows[0]) if rows else None
        return found

    def later_amendments(self, security: Security, limit: int = 10) -> list[Filing]:
        """Amendments EDGAR accepted after the knowledge time to filings it had accepted
        by then, oldest first, at most `limit`: a 10-Q/A that changed a 10-Q a reader
        at the knowledge time could see. An amendment whose original came later too, or
        isn't known, isn't listed."""
        if limit < 1:
            raise ValueError(f"limit must be at least 1, not {limit}")
        ciks = self._view._ciks(security.security_id, security.cik)
        if not ciks:
            return []
        in_ciks = f"cik IN ({', '.join('?' * len(ciks))})"
        rows = self._view._select(
            "filings",
            where=(
                f"{in_ciks} AND is_amendment AND available_at > ? AND amends IN "
                f"(SELECT accession_number FROM filings WHERE {in_ciks} "
                "AND available_at <= ?)"
            ),
            params=[*ciks, self.knowledge_time, *ciks, self.knowledge_time],
            latest_per_key=True,
            order_by="available_at, accession_number",
            limit=limit,
        )
        return [_filing(security, row) for row in rows]

    def later_versions(self, observation: MacroObservation) -> list[MacroObservation]:
        """The versions of a macro observation published after the knowledge time,
        oldest first. May 2020's unemployment rate was 13.3% on June 5, 2020, and was
        revised to 13.2% on January 7, 2022."""
        return [
            version
            for version in self._view.get_revision_history(
                observation.series_id, observation.period
            )
            if version.available_at > self.knowledge_time
        ]

    def later_quarter_versions(
        self, security: Security, quarter: Fundamental
    ) -> list[Fundamental]:
        """How a quarter of a standard metric changed after the knowledge time, oldest
        first: each time a later filing changed its value, its concept, or the filings
        it cites, the quarter as `get_fundamentals_as_of` would have given it right
        after that filing.

        Apple's revenue for the quarter ended March 28, 2020, known on June 5, 2020
        from its 10-Q, was re-reported in the fiscal 2020 10-K, accepted on October
        29, 2020, and again in the next year's 10-Q, accepted on April 28, 2021.
        """
        standard = metrics.metric(quarter.metric)
        ciks = self._view._ciks(security.security_id, security.cik)
        if not ciks:
            return []
        concepts = standard.concepts_for(security.security_id)
        names = standard.parts_for(security.security_id)
        rows = self._view._select(
            "xbrl_facts",
            where=(
                f"cik IN ({', '.join('?' * len(ciks))}) AND unit = ? "
                f"AND concept IN ({', '.join('?' * len(names))})"
            ),
            params=[*ciks, standard.unit, *names],
        )
        later = {
            row["available_at"]
            for row in rows
            if row["available_at"] > self.knowledge_time
        }
        found: list[Fundamental] = []
        current = quarter
        for moment in sorted(later):
            known = [row for row in rows if row["available_at"] <= moment]
            match = next(
                (
                    candidate
                    for candidate in fundamentals.quarterly_values(
                        known, standard, concepts
                    )
                    if candidate.period_end == quarter.period_end
                ),
                None,
            )
            if match is None:
                continue
            version = _fundamental(security, standard, match)
            if (version.value, version.concept, version.accession_numbers) != (
                current.value,
                current.concept,
                current.accession_numbers,
            ):
                found.append(version)
                current = version
        return found

    def universe_changes(self, security: Security) -> list[UniverseChange]:
        """The security's universe memberships that changed after the knowledge time,
        oldest first. On June 5, 2020, Tesla wasn't in universe v1 yet: it joined on
        December 21, 2020, the day it joined the S&P 500."""
        rows = self._view._select(
            "universe_members",
            where="security_id = ? AND available_at > ?",
            params=[security.security_id, self.knowledge_time],
            order_by="available_at, universe",
        )
        return [
            UniverseChange(
                universe=row["universe"],
                security_id=row["security_id"],
                change="joins" if row["removed"] is None else "leaves",
                effective=row["added"] if row["removed"] is None else row["removed"],
                available_at=row["available_at"],
                time_assumed=row["time_assumed"],
                source=row["source"],
                source_ref=row["source_ref"],
            )
            for row in rows
        ]

    def close(self) -> None:
        """Close the view it reads through."""
        self._view.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"LookAhead(knowledge_time={self.knowledge_time.isoformat()}, "
            f"horizon={self.horizon.isoformat()}, "
            f"data_version={self._view.data_version!r})"
        )
