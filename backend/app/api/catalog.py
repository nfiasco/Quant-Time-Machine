"""GET /v1/catalog/series: the series forms and search boxes can offer (S8.5), each with
how much of it was published by the knowledge time, like every other read."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api import examples
from app.api.conventions import DataResponse, View

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
