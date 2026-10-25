"""GET /v1/filings/{ticker} and /latest: the SEC filings EDGAR had accepted by the
knowledge time, counted from their acceptance times."""

from collections.abc import Sequence
from datetime import date
from typing import Annotated, Literal, get_args

from fastapi import APIRouter, Path, Query
from pydantic import Field

from app.api import examples
from app.api.conventions import DataResponse, Provenance, View
from app.data.timeutil import describe_time
from app.data.view import PointInTimeView

router = APIRouter(prefix="/filings", tags=["filings"])

FormFamily = Literal["10-K", "10-Q", "8-K"]
"""A form a reader asks for: the keys of FORM_FAMILIES in app/data/sources/edgar.py (a
test keeps them equal). "10-K" also covers 10-K405 and 10-KT, and "10-Q" covers 10-QT."""

ALL_FORMS: tuple[FormFamily, ...] = get_args(FormFamily)

Ticker = Annotated[
    str, Path(description="A ticker as used at the knowledge time, in any case.")
]
IncludeAmendments = Annotated[
    bool, Query(description="Also count amendments, such as a 10-Q/A.")
]


class Filing(Provenance):
    """An SEC filing that EDGAR had accepted by the knowledge time (S5.4)."""

    ticker: str = Field(description="The ticker at the knowledge time.")
    cik: int = Field(description="The filer's SEC identifier.")
    company_name: str = Field(description="The company's name at the knowledge time.")
    accession_number: str
    form: str = Field(description="As filed, such as 10-Q, 10-K405, or 10-Q/A.")
    is_amendment: bool
    amends: str | None = Field(
        description="The accession number of the filing an amendment changes, if known."
    )
    period_of_report: date | None
    filing_date: date = Field(
        description=(
            "For display only: filings accepted after 5:30 PM ET get the next business "
            "day. available_at is when the filing became public."
        )
    )
    document_url: str | None
    index_url: str


class FilingResponse(DataResponse[Filing | None]):
    """The latest filing of a form known at the knowledge time, or null with a reason."""


class FilingListResponse(DataResponse[list[Filing]]):
    """The filings known at the knowledge time, newest first, or [] with a reason."""


@router.get("/{ticker}/latest", responses=examples.LATEST_FILING)
def get_latest_filing(
    ticker: Ticker,
    view: View,
    form: Annotated[FormFamily, Query(description="The form family.")] = "10-Q",
    include_amendments: IncludeAmendments = False,
) -> FilingResponse:
    """The latest filing of one form that EDGAR had accepted by the knowledge time.
    It counts from the acceptance time, never the period end or the filing date."""
    filing = view.get_latest_filing_as_of(ticker, form, include_amendments)
    reason = None if filing else _nothing_accepted(view, ticker, form)
    return FilingResponse(
        knowledge_time=view.knowledge_time,
        data_version=view.data_version,
        data=filing,
        reason=reason,
    )


@router.get("/{ticker}", responses=examples.FILINGS)
def list_filings(
    ticker: Ticker,
    view: View,
    form: Annotated[
        FormFamily | None, Query(description="One form family. Default: all three.")
    ] = None,
    include_amendments: IncludeAmendments = False,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> FilingListResponse:
    """The filings EDGAR had accepted by the knowledge time, newest first."""
    forms = ALL_FORMS if form is None else (form,)
    filings = view.list_filings_as_of(ticker, forms, include_amendments, limit)
    reason = None
    if not filings:
        reason = _nothing_accepted(view, ticker, f"{_any_of(forms)} filings")
    return FilingListResponse(
        knowledge_time=view.knowledge_time,
        data_version=view.data_version,
        data=filings,
        reason=reason,
    )


def _nothing_accepted(view: PointInTimeView, ticker: str, what: str) -> str:
    """Why a search found nothing: "No 10-Q from Facebook, Inc. had been accepted…"."""
    security = view.resolve_ticker(ticker)
    return (
        f"No {what} from {security.name or security.ticker} had been accepted by "
        f"EDGAR by {describe_time(view.knowledge_time)}."
    )


def _any_of(forms: Sequence[str]) -> str:
    """For example "10-K, 10-Q, or 8-K"."""
    if len(forms) <= 2:
        return " or ".join(forms)
    return f"{', '.join(forms[:-1])}, or {forms[-1]}"
