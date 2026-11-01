"""GET /v1/fundamentals/{ticker}: a company's last quarters of a standard metric, as
filed by the knowledge time (S5.7)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from pydantic import Field

from app.api import examples
from app.api.conventions import DataResponse, Provenance, View
from app.data.sources.metrics import METRICS
from app.data.timeutil import describe_time
from app.data.view import PointInTimeView

router = APIRouter(prefix="/fundamentals", tags=["fundamentals"])

MetricName = Literal[
    "revenue",
    "net_income",
    "eps_diluted",
    "operating_cash_flow",
    "total_assets",
    "shares_outstanding",
]
"""A metric a reader asks for: the names in app/data/sources/metrics.toml (a test keeps
them equal)."""


class Fundamental(Provenance):
    """One quarter of a standard metric, as known at the knowledge time (S5.7). For an
    instant metric, such as total assets, it's the value on one date."""

    ticker: str = Field(description="The ticker at the knowledge time.")
    cik: int | None = Field(description="The company's SEC identifier at the time.")
    metric: str = Field(description="The standard metric, such as revenue.")
    concept: str = Field(
        description=(
            "The XBRL concept the value came from, such as "
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax."
        )
    )
    unit: str = Field(description="USD, USD/shares, or shares.")
    period_start: date | None = Field(
        description="Null for an instant, such as total assets on a balance-sheet date."
    )
    period_end: date
    fiscal_year: int | None = Field(
        description=(
            "The company's fiscal year, from the filing that reported the period as its "
            "own. Null if no filing in our data did."
        )
    )
    fiscal_period: Literal["Q1", "Q2", "Q3", "Q4"] | None = Field(
        description="The fiscal quarter, from the same filing as fiscal_year."
    )
    value: float
    derived: bool = Field(
        description=(
            "True for a quarter no filing reported, computed from two year-to-date "
            "totals filed by then: a fourth quarter is the full year minus the first "
            "nine months."
        )
    )
    accession_numbers: list[str] = Field(
        description=(
            "The filings the value came from: one, or two for a derived quarter, the "
            "longer total's first."
        )
    )


class FundamentalListResponse(DataResponse[list[Fundamental]]):
    """A metric's last quarters known at the knowledge time, oldest first, or [] with a
    reason."""


@router.get("/{ticker}", responses=examples.FUNDAMENTALS)
def get_fundamentals(
    ticker: Annotated[
        str, Path(description="A ticker as used at the knowledge time, in any case.")
    ],
    view: View,
    metric: Annotated[MetricName, Query(description="The standard metric.")] = (
        "revenue"
    ),
    quarters: Annotated[
        int, Query(ge=1, le=40, description="How many of the latest quarters.")
    ] = 8,
) -> FundamentalListResponse:
    """A company's last quarters of a standard metric as filed by the knowledge time,
    oldest first. Each is the latest value filed for its quarter. A quarter no filing
    reported is derived from two year-to-date totals, such as the full year minus the
    first nine months, and cites both filings."""
    found = view.get_fundamentals_as_of(ticker, metric, quarters)
    return FundamentalListResponse(
        knowledge_time=view.knowledge_time,
        data_version=view.data_version,
        data=found,
        reason=None if found else _nothing_reported(view, ticker, metric),
    )


def _nothing_reported(view: PointInTimeView, ticker: str, metric: str) -> str:
    """Why nothing came back: "No filing EDGAR had accepted from … reported …"."""
    security = view.resolve_ticker(ticker)
    standard = METRICS[metric]
    what = (
        standard.label
        if standard.period == "instant"
        else f"quarterly {standard.label}"
    )
    return (
        f"No filing EDGAR had accepted from {security.name or security.ticker} by "
        f"{describe_time(view.knowledge_time)} reported {what}."
    )
