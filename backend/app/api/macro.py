"""GET /v1/macro/{series_id}: a macro series as it was published at the knowledge time."""

import re
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query
from pydantic import BeforeValidator, Field
from pydantic_core import PydanticCustomError

from app.api import examples
from app.api.conventions import DataResponse, Provenance, View
from app.data.timeutil import describe_time

router = APIRouter(prefix="/macro", tags=["macro"])


class MacroObservation(Provenance):
    """One observation of a macro series, as published by the knowledge time (S4.4)."""

    series_id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str
    release: str = Field(
        description='The release it comes out in, such as "Employment Situation".'
    )
    period: date = Field(description="The observation date: 2020-05-01 is May 2020.")
    value: float | None = Field(
        description="Null when the source published the observation as missing."
    )
    vintage_date: date = Field(
        description="When this version was published (ALFRED's realtime_start)."
    )


class MacroResponse(DataResponse[MacroObservation | None]):
    """A macro observation as published at the knowledge time, or null with a reason."""


def _iso_date(value: Any) -> Any:
    # A plain date parameter would also take 1585699200 or 2020-04-01T00:00:00.
    if isinstance(value, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise PydanticCustomError("date_format", "Use a date such as 2020-04-01.")
    return value


IsoDate = Annotated[date, BeforeValidator(_iso_date)]
"""A date written YYYY-MM-DD, and nothing else."""


@router.get("/{series_id}", responses=examples.MACRO)
def get_macro(
    series_id: Annotated[
        str, Path(description="A series in our catalog, such as UNRATE, in any case.")
    ],
    view: View,
    period: Annotated[
        IsoDate | None,
        Query(
            description=(
                "An observation date, such as 2020-04-01 for April 2020. Default: the "
                "latest period published."
            ),
        ),
    ] = None,
) -> MacroResponse:
    """A series' latest observation as published at the knowledge time, or the latest
    version of one period's. Revisions published later stay invisible."""
    observation = view.get_macro_as_of(series_id, period)
    reason = None
    if observation is None:
        what = f"No {series_id.strip().upper()} value"
        if period is not None:
            what += f" for {period.isoformat()}"
        reason = f"{what} had been published by {describe_time(view.knowledge_time)}."
    return MacroResponse(
        knowledge_time=view.knowledge_time,
        data_version=view.data_version,
        data=observation,
        reason=reason,
    )
