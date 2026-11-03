"""GET /v1/catalog/series and /companies: the choices forms and search boxes can offer
(S8.5).

Both are as known at the knowledge time, like every other read: the universe's members
then, under the tickers and names they used then, and how far each one's data reaches
by then.
"""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api import examples
from app.api.conventions import DataResponse, View
from app.data.sources.universes import HISTORY_START, UNIVERSES
from app.data.timeutil import describe_time

router = APIRouter(prefix="/catalog", tags=["catalog"])


class DateRange(BaseModel):
    """The first and last dates of something in our data, both included."""

    model_config = ConfigDict(from_attributes=True)

    first: date
    last: date


class CatalogSeries(BaseModel):
    """A series in our catalog, and how much of it was published by the knowledge time."""

    model_config = ConfigDict(from_attributes=True)

    series_id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str
    release: str = Field(
        description='The release it comes out in, such as "Employment Situation".'
    )
    observations: DateRange | None = Field(
        description=(
            "The first and last observation dates published by then: 2020-05-01 is May "
            "2020. Null if none was."
        )
    )
    vintages: DateRange | None = Field(
        description=(
            "The dates of the first and last vintages published by then. Null if none "
            "was. ALFRED's archive starts later than the data, so an observation is "
            "unknown until the first vintage that has it."
        )
    )


class SeriesCatalogResponse(DataResponse[list[CatalogSeries]]):
    """Every series in our catalog, with how much of it was published by the knowledge
    time."""


class CatalogCompany(BaseModel):
    """A universe's member at the knowledge time, and how far its data reaches by then."""

    model_config = ConfigDict(from_attributes=True)

    ticker: str | None = Field(
        description=(
            "The ticker at the knowledge time: FB for Facebook in 2020. Null if it had "
            "stopped trading but hadn't left the universe yet."
        )
    )
    name: str = Field(description="The name at the knowledge time.")
    cik: int | None = Field(description="Null for a security without one.")
    universe: str = Field(description="Its universe, such as starter_large_caps.")
    added: date = Field(description="The first day of its membership.")
    prices: DateRange | None = Field(
        description="The sessions of its first and last daily bars known then."
    )
    filings: DateRange | None = Field(
        description=(
            "The New York dates on which EDGAR accepted its first and last 10-K, 10-Q, "
            "or 8-K, or an amendment, known then."
        )
    )
    fundamentals: DateRange | None = Field(
        description=(
            "The New York dates on which EDGAR accepted the first and last filings "
            "whose XBRL facts we have, known then."
        )
    )


class CompanyCatalogResponse(DataResponse[list[CatalogCompany]]):
    """The universe's members at the knowledge time, or [] with a reason."""


@router.get("/series", responses=examples.CATALOG_SERIES)
def list_series(view: View) -> SeriesCatalogResponse:
    """Every series in our catalog, in its order, with how much of it was published by
    the knowledge time: its first and last observations, and its first and last
    vintages. Both are null for a series with nothing published yet."""
    return SeriesCatalogResponse(
        knowledge_time=view.knowledge_time,
        data_version=view.data_version,
        data=view.series_coverage(),
    )


@router.get("/companies", responses=examples.CATALOG_COMPANIES)
def list_companies(view: View) -> CompanyCatalogResponse:
    """The members of each universe at the knowledge time (for now, universe v1,
    starter_large_caps), under the tickers and names they used then. Each comes with how
    far its prices, filings, and XBRL facts reach by then."""
    companies = [
        company
        for universe in UNIVERSES.by_name
        for company in view.universe_coverage(universe)
    ]
    reason = None
    if not companies:
        reason = (
            f"No company was in a universe as of {describe_time(view.knowledge_time)}: "
            f"membership history starts on {HISTORY_START.isoformat()}."
        )
    return CompanyCatalogResponse(
        knowledge_time=view.knowledge_time,
        data_version=view.data_version,
        data=companies,
        reason=reason,
    )
