"""GET /v1/snapshot: what was known at a moment, and what wasn't yet (S8.3).

The "known" half reads the request's `PointInTimeView`, like every other endpoint. The
"not yet known" half reads app/data/look_ahead.py, which deliberately looks past the
knowledge time, only to teach. This is the one module allowed to import it
(tests/test_look_ahead.py).

Raw prices follow SERVE_RAW_PRICES, but unlike GET /v1/prices, the snapshot never
answers 403. With prices off, each latest bar keeps its date and when it became known,
and loses its prices (`prices_withheld`). A next bar never has prices: they weren't known.
"""

from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field

from app.api import examples
from app.api.conventions import (
    AppSettings,
    DataResponse,
    DataVersion,
    KnowledgeTime,
    NewYorkTime,
    Provenance,
    View,
)
from app.api.filings import Filing
from app.api.fundamentals import Fundamental
from app.api.macro import MacroObservation
from app.api.prices import PriceBar
from app.data import records
from app.data.look_ahead import LookAhead
from app.data.sources.edgar import FORM_FAMILIES
from app.data.sources.universes import UNIVERSES
from app.data.store import store_dir

router = APIRouter(tags=["snapshot"])

MAX_ENTRIES = 10
"""The most tickers, and the most series, one snapshot takes."""


def look_ahead(
    knowledge_time: KnowledgeTime, settings: AppSettings, data_version: DataVersion
) -> Iterator[LookAhead]:
    """The request's look past `as_of`, through the same data version as its view."""
    with LookAhead(
        knowledge_time, data_version=data_version, store=store_dir(settings.data_dir)
    ) as ahead:
        yield ahead


Ahead = Annotated[LookAhead, Depends(look_ahead, scope="function")]


class FilingsByForm(BaseModel):
    """One filing of each form family, or null."""

    model_config = ConfigDict(serialize_by_alias=True, validate_by_name=True)

    ten_k: Filing | None = Field(alias="10-K")
    ten_q: Filing | None = Field(alias="10-Q")
    eight_k: Filing | None = Field(alias="8-K")


class Membership(Provenance):
    """A universe a company was a member of at the knowledge time."""

    universe: str = Field(description="Such as starter_large_caps.")
    added: date = Field(description="The first day of the membership.")


class SnapshotCompanyKnown(BaseModel):
    """What was known about a company at the knowledge time."""

    ticker: str = Field(description="The ticker at the knowledge time.")
    cik: int | None = Field(description="Null for a security without one.")
    company_name: str = Field(description="The name at the knowledge time.")
    prices_withheld: bool = Field(
        description=(
            "True when this server doesn't serve raw prices (SERVE_RAW_PRICES): "
            "latest_bar keeps its session_date and available_at, but its prices and "
            "volume are null."
        )
    )
    latest_bar: PriceBar | None = Field(
        description=(
            "The latest daily bar whose session had closed, as in GET "
            "/v1/prices/{ticker}. Null if our data has none."
        )
    )
    latest_filings: FilingsByForm = Field(
        description="The latest original 10-K, 10-Q, and 8-K EDGAR had accepted."
    )
    latest_revenue: Fundamental | None = Field(
        description=(
            "The latest quarter of revenue filed, as in GET /v1/fundamentals/{ticker}. "
            "Null if none was."
        )
    )
    universes: list[Membership] = Field(description="The universes it was in.")


class SnapshotSeriesKnown(BaseModel):
    """What was known about a series at the knowledge time."""

    series_id: str
    latest: MacroObservation | None = Field(
        description=(
            "The latest observation published, as in GET /v1/macro/{series_id}. Null "
            "if none was."
        )
    )


class SnapshotKnown(BaseModel):
    """Public at or before the knowledge time, read like every other endpoint."""

    companies: list[SnapshotCompanyKnown]
    series: list[SnapshotSeriesKnown]


class NextBar(BaseModel):
    """When a daily bar became known, without its prices: they weren't known yet."""

    model_config = ConfigDict(from_attributes=True)

    session_date: date
    available_at: NewYorkTime = Field(description="The session's close.")


class UniverseChange(Provenance):
    """A company joining or leaving a universe after the knowledge time."""

    universe: str = Field(description="Such as starter_large_caps.")
    change: Literal["joins", "leaves"]
    effective: date = Field(
        description=(
            "The first day of the change: the day it joined, or the first day it "
            "wasn't a member any more. available_at is 00:00 ET that day."
        )
    )


class SnapshotCompanyNotYetKnown(BaseModel):
    """What became public about a company after the knowledge time."""

    ticker: str = Field(description="The ticker at the knowledge time.")
    next_bar: NextBar | None = Field(
        description="The first bar after the knowledge time. Null if our data has none."
    )
    next_filings: FilingsByForm = Field(
        description=(
            "The first original 10-K, 10-Q, and 8-K EDGAR accepted after the knowledge "
            "time."
        )
    )
    later_amendments: list[Filing] = Field(
        description=(
            "Amendments accepted later to filings accepted by the knowledge time, "
            "oldest first, up to 10."
        )
    )
    later_revenue: list[Fundamental] = Field(
        description=(
            "Each later version of the quarter in latest_revenue, oldest first: a "
            "re-report or a restatement, as known right after the filing that changed "
            "it."
        )
    )
    universe_changes: list[UniverseChange] = Field(
        description="Its later universe joins and leaves, oldest first."
    )


class SnapshotSeriesNotYetKnown(BaseModel):
    """What became public about a series after the knowledge time."""

    series_id: str
    period: date | None = Field(
        description="The observation known's latest is. Null if none was published."
    )
    revisions: list[MacroObservation] = Field(
        description=(
            "Its versions published later, oldest first. The last is its value in our "
            "data now."
        )
    )


class SnapshotNotYetKnown(BaseModel):
    """Public after the knowledge time, read by the look-ahead module only to teach.
    Never feed it into anything else."""

    companies: list[SnapshotCompanyNotYetKnown]
    series: list[SnapshotSeriesNotYetKnown]


class Snapshot(BaseModel):
    """What was known at a moment, and what wasn't yet."""

    known: SnapshotKnown
    not_yet_known: SnapshotNotYetKnown


class SnapshotResponse(DataResponse[Snapshot]):
    """A snapshot of the knowledge time. `data` is never null, so `reason` is always
    null."""


@router.get("/snapshot", responses=examples.SNAPSHOT)
def get_snapshot(
    view: View,
    ahead: Ahead,
    settings: AppSettings,
    tickers: Annotated[
        str | None,
        Query(
            description=(
                "Comma-separated tickers as used at the knowledge time, in any case, "
                f"such as AAPL,TSLA. Up to {MAX_ENTRIES}."
            )
        ),
    ] = None,
    series: Annotated[
        str | None,
        Query(
            description=(
                "Comma-separated series in our catalog, such as UNRATE,FEDFUNDS. Up to "
                f"{MAX_ENTRIES}."
            )
        ),
    ] = None,
) -> SnapshotResponse:
    """What was known at the knowledge time, and what wasn't yet, for some companies and
    series: the June 5, 2020 table in doc/time-model.md. `known` is each company's
    latest bar, filings, and revenue quarter, its universes, and each series' latest
    observation. `not_yet_known` is what came after: the next bar and filings, later
    amendments, later versions of that revenue quarter, universe changes, and later
    revisions of each observation shown. A repeated entry counts once, and results
    keep the order given."""
    symbols = _entries(tickers, "tickers")
    series_ids = _entries(series, "series")
    if not symbols and not series_ids:
        raise _invalid("tickers", "tickers or series is required.", tickers)

    withheld = not settings.serve_raw_prices
    members = [
        member
        for universe in (UNIVERSES.by_name if symbols else ())
        for member in view.universe_as_of(universe)
    ]
    known_companies, later_companies = [], []
    for symbol in symbols:
        security = view.resolve_ticker(symbol)
        quarters = view.get_fundamentals_as_of(symbol, "revenue", quarters=1)
        revenue = quarters[-1] if quarters else None
        known_companies.append(
            SnapshotCompanyKnown(
                ticker=security.ticker,
                cik=security.cik,
                company_name=security.name,
                prices_withheld=withheld,
                latest_bar=_without_prices(view.get_price_as_of(symbol), withheld),
                latest_filings=_by_form(
                    {
                        family: view.get_latest_filing_as_of(symbol, family)
                        for family in FORM_FAMILIES
                    }
                ),
                latest_revenue=revenue,
                universes=[
                    member
                    for member in members
                    if member.security_id == security.security_id
                ],
            )
        )
        later_companies.append(
            SnapshotCompanyNotYetKnown(
                ticker=security.ticker,
                next_bar=ahead.next_bar(security),
                next_filings=_by_form(ahead.next_filings(security)),
                later_amendments=ahead.later_amendments(security),
                later_revenue=(
                    []
                    if revenue is None
                    else ahead.later_quarter_versions(security, revenue)
                ),
                universe_changes=ahead.universe_changes(security),
            )
        )

    known_series, later_series = [], []
    for series_id in series_ids:
        latest = view.get_macro_as_of(series_id)
        known_series.append(SnapshotSeriesKnown(series_id=series_id, latest=latest))
        later_series.append(
            SnapshotSeriesNotYetKnown(
                series_id=series_id,
                period=None if latest is None else latest.period,
                revisions=[] if latest is None else ahead.later_versions(latest),
            )
        )

    return SnapshotResponse(
        knowledge_time=view.knowledge_time,
        data_version=view.data_version,
        data=Snapshot(
            known=SnapshotKnown(companies=known_companies, series=known_series),
            not_yet_known=SnapshotNotYetKnown(
                companies=later_companies, series=later_series
            ),
        ),
    )


def _entries(text: str | None, field: str) -> list[str]:
    """A comma-separated parameter's entries: trimmed and in capitals, blank ones
    dropped, each once, in the order given."""
    entries = list(
        dict.fromkeys(
            entry.strip().upper() for entry in (text or "").split(",") if entry.strip()
        )
    )
    if len(entries) > MAX_ENTRIES:
        raise _invalid(field, f"{field} can list at most {MAX_ENTRIES}.", text)
    return entries


def _invalid(field: str, message: str, value: object) -> RequestValidationError:
    """A 422 for one query parameter, with our own sentence (app/api/errors.py)."""
    return RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("query", field),
                "msg": message,
                "input": value,
            }
        ]
    )


def _without_prices(
    bar: records.PriceBar | None, withheld: bool
) -> records.PriceBar | None:
    """The bar, with its prices and volume removed when they're withheld."""
    if bar is None or not withheld:
        return bar
    return replace(bar, open=None, high=None, low=None, close=None, volume=None)


def _by_form(filings: Mapping[str, records.Filing | None]) -> FilingsByForm:
    """Filings keyed by form family, such as "10-Q", as a model."""
    return FilingsByForm.model_validate(filings)
