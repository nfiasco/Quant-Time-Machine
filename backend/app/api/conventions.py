"""Conventions every /v1 endpoint follows (S8.1; the contract is doc/api-v1.md).

- **Knowledge time.** Each endpoint takes `as_of`, parsed by `parse_knowledge_time`
  (doc/time-model.md, rule 3): `2020-06-05` means 09:30 ET. It's required, because an
  API default of "now" is a classic way for look-ahead to sneak in.
- **Reads.** A handler that reads data takes `view: View`: one `PointInTimeView` per
  request, bound to `as_of` and pinned to the app store's newest data version (S3.7),
  and closed once the response is built.
- **Echo.** Every response carries `knowledge_time` (the exact instant used) and
  `data_version` (the data version read, null only for a store that has none yet).
  Every timestamp is written in New York time with its offset (`NewYorkTime`).
- **Envelope.** Data endpoints answer with a `DataResponse`. Its `data` is null (or []
  for a list) when nothing was known yet, and `reason` then says why.
- **Errors.** app/api/errors.py turns every error into the contract's error body.
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Literal, Self

from fastapi import Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.config import Settings
from app.data.store import store_dir
from app.data.timeutil import ET, KnowledgeTimeError, parse_knowledge_time
from app.data.versions import latest_data_version
from app.data.view import PointInTimeView


def _in_new_york(value: datetime) -> datetime:
    return value.astimezone(ET)


NewYorkTime = Annotated[AwareDatetime, AfterValidator(_in_new_york)]
"""A timestamp written in New York time with its offset (D12): 2020-06-05T09:30:00-04:00.
Fractions of a second appear only when they aren't zero."""


def knowledge_time(
    as_of: Annotated[
        str,
        Query(
            description=(
                "The moment to answer as of. A date means 09:30 ET that day. A date and "
                "time without an offset is New York time, except in the daylight-saving "
                "changes, which need an offset. A timestamp with Z or an offset is used "
                "as given (encode '+' as %2B)."
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


def app_settings(request: Request) -> Settings:
    """The settings the app was built with (see `create_app`)."""
    return request.app.state.settings


AppSettings = Annotated[Settings, Depends(app_settings)]
"""An endpoint or dependency parameter for the app's settings."""


def newest_data_version(settings: AppSettings) -> str | None:
    """The app store's newest data version, which this request reads; None if no
    ingestion run has written one yet."""
    return latest_data_version(store_dir(settings.data_dir))


DataVersion = Annotated[str | None, Depends(newest_data_version)]
"""An endpoint or dependency parameter for the data version the request reads."""


def point_in_time_view(
    knowledge_time: KnowledgeTime, settings: AppSettings, data_version: DataVersion
) -> Iterator[PointInTimeView]:
    """One view per request: the app's store as it was known at `as_of`, pinned to its
    newest data version."""
    with PointInTimeView(
        knowledge_time, data_version=data_version, store=store_dir(settings.data_dir)
    ) as view:
        yield view


View = Annotated[PointInTimeView, Depends(point_in_time_view, scope="function")]
"""An endpoint parameter for the request's view, closed once the response is built.
Echo `view.knowledge_time` and `view.data_version` in the response."""


class AsOfResponse(BaseModel):
    """What every /v1 response says about its own answer."""

    # Marks fields with defaults, such as `reason`, as required in the response schema,
    # since every response includes them (S8.6 generates TypeScript types from it).
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    knowledge_time: NewYorkTime = Field(
        description="The exact instant this answer is as of, in New York time."
    )
    data_version: str | None = Field(
        description=(
            "The data version read: the newest in the store when the request arrived, "
            "such as 20261101T143005Z. Null only if the store has none yet."
        )
    )


class DataResponse[T](AsOfResponse):
    """An answer as known at the knowledge time, or null (or []) with the reason why.

    Each endpoint declares a named subclass, such as `MacroResponse`, so the OpenAPI
    schema (and the types generated from it) gets a readable name.
    """

    data: T = Field(
        description="The answer: null, or [] for a list, when nothing was known yet."
    )
    reason: str | None = Field(
        default=None,
        description=(
            "Why `data` is null or empty, as one sentence the page can show as is. "
            "Null otherwise."
        ),
    )

    @model_validator(mode="after")
    def _reason_exactly_when_empty(self) -> Self:
        empty = self.data is None or self.data == []
        if empty != bool(self.reason):
            raise ValueError("a reason is required exactly when data is null or empty")
        return self


class Provenance(BaseModel):
    """Where a record came from and when it became public (doc/time-model.md).

    Models built on it read the records in app/data/records.py by attribute, so an
    endpoint can return a record as `data` as it is.
    """

    model_config = ConfigDict(from_attributes=True)

    available_at: NewYorkTime = Field(description="When the record became public.")
    time_assumed: bool = Field(
        description=(
            "True when `available_at` is a conservative default rather than a known "
            "time (rule 11). Show it as a caveat."
        )
    )
    source: Literal["alfred", "edgar", "tiingo"] = Field(
        description="Where the record came from."
    )
    source_ref: str = Field(
        description=(
            "A pointer to the exact source item, such as an accession number or a "
            "vintage."
        )
    )
