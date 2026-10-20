"""Conventions every /v1 endpoint follows (S8.1).

- **Knowledge time.** Each endpoint takes `as_of`, parsed by `parse_knowledge_time`
  (doc/time-model.md, rule 3): `2020-06-05` means 09:30 ET. It's required, because an
  API default of "now" is a classic way for look-ahead to sneak in.
- **Echo.** Every response carries `knowledge_time` (the exact UTC instant used) and
  `data_version` (null until runs can pin data versions, S3.7). Build responses from
  `AsOfResponse` or `ValueResponse`.
- **Errors.** 404 for an unknown ticker or series (`NotFoundError`), 422 for invalid
  input, and 200 with `value: null` plus a `reason` when nothing was known yet
  (`LookAheadError`). Error bodies keep FastAPI's `{"detail": ...}` shape.
"""

from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.data.errors import LookAheadError, NotFoundError
from app.data.timeutil import KnowledgeTimeError, parse_knowledge_time


def knowledge_time(
    as_of: Annotated[
        str,
        Query(
            description=(
                "The moment to answer as of. A date means 09:30 ET that day. A date and "
                "time without an offset is New York time. A timestamp with Z or an "
                "offset is used as given (encode '+' as %2B)."
            ),
            openapi_examples={
                "date": {"summary": "A date: 09:30 ET", "value": "2020-06-05"},
                "new_york": {
                    "summary": "A New York time",
                    "value": "2020-06-05T09:30",
                },
                "utc": {"summary": "A UTC timestamp", "value": "2020-06-05T13:30:00Z"},
            },
        ),
    ],
) -> datetime:
    """Parse the `as_of` query parameter into an aware UTC datetime, or answer 422."""
    try:
        return parse_knowledge_time(as_of)
    except KnowledgeTimeError as error:
        detail = {
            "type": "value_error",
            "loc": ("query", "as_of"),
            "msg": str(error),
            "input": as_of,
        }
        raise RequestValidationError([detail]) from None


KnowledgeTime = Annotated[datetime, Depends(knowledge_time)]
"""An endpoint parameter for the knowledge time, read from `as_of`."""


class AsOfResponse(BaseModel):
    """What every /v1 response says about its own answer."""

    knowledge_time: datetime = Field(
        description="The exact instant this answer is as of, in UTC."
    )
    data_version: str | None = Field(
        description="The data version read. Null until data versions exist (S3.7)."
    )


class ValueResponse[T](AsOfResponse):
    """One value as known at the knowledge time, or null with the reason why."""

    value: T | None
    reason: str | None = Field(
        default=None,
        description="Why `value` is null, for example because nothing was known yet.",
    )


async def _not_found(request: Request, error: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(error)})


async def _not_known_yet(request: Request, error: LookAheadError) -> JSONResponse:
    body = ValueResponse[None](
        knowledge_time=error.knowledge_time,
        data_version=error.data_version,
        value=None,
        reason=str(error),
    )
    return JSONResponse(status_code=200, content=body.model_dump(mode="json"))


def add_error_handlers(app: FastAPI) -> None:
    """Map the data layer's errors to the responses described above."""
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(LookAheadError, _not_known_yet)
