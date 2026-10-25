"""GET /v1/prices/{ticker}: a security's latest daily bar as known at the knowledge time.

Tiingo's terms allow internal use only (doc/data-sources.md, D2), so every route here
answers 403 `prices_restricted` unless the SERVE_RAW_PRICES setting is on. Turn it on
only on your own machine until display rights are settled.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import Field

from app.api import examples
from app.api.conventions import AppSettings, DataResponse, Provenance, View
from app.api.errors import ApiError
from app.data.timeutil import describe_time

RESTRICTED_MESSAGE = (
    "Raw prices are turned off on this server, because our price vendor's terms don't "
    "allow showing them publicly yet."
)


def require_raw_prices(settings: AppSettings) -> None:
    """Answer 403 unless this deployment may serve raw prices (SERVE_RAW_PRICES)."""
    if not settings.serve_raw_prices:
        raise ApiError(403, "prices_restricted", RESTRICTED_MESSAGE)


# A router dependency runs before the route's own parameters are checked, so a
# deployment without prices answers 403 to every request.
router = APIRouter(
    prefix="/prices", tags=["prices"], dependencies=[Depends(require_raw_prices)]
)


class PriceBar(Provenance):
    """One raw daily bar, as traded, never adjusted for later splits or dividends."""

    ticker: str = Field(
        description="The ticker at the knowledge time: FB for Facebook's bars in 2020."
    )
    cik: int | None = Field(description="Null for a security without one.")
    session_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None


class PriceResponse(DataResponse[PriceBar | None]):
    """The latest bar known at the knowledge time, or null with a reason."""


@router.get("/{ticker}", responses=examples.PRICES)
def get_price(
    ticker: Annotated[
        str,
        Path(description="A ticker as used at the knowledge time, in any case."),
    ],
    view: View,
) -> PriceResponse:
    """The latest daily bar whose session had closed by the knowledge time: at 09:30 ET,
    the day before's. A bar is known at its session's close, 16:00 ET, or 13:00 ET on an
    early-close day."""
    bar = view.get_price_as_of(ticker)
    reason = None
    if bar is None:
        reason = (
            f"Our data has no daily bar for {ticker.strip().upper()} from a session "
            f"that had closed by {describe_time(view.knowledge_time)}."
        )
    return PriceResponse(
        knowledge_time=view.knowledge_time,
        data_version=view.data_version,
        data=bar,
        reason=reason,
    )
