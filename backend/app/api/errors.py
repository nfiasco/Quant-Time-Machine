"""The error body every API error uses, and the handlers and middleware that produce it.

Every error answers with the shape in the contract (doc/api-v1.md):

    {"error": {"code": "invalid_request", "message": "...", "details": [...]}}

`message` is a sentence the page can show as is. `details` lists each invalid field for
`invalid_request` and is empty otherwise. "Nothing was known yet" isn't an error: a
`LookAheadError` answers 200 with `data: null` and the reason.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.conventions import DataResponse
from app.data.errors import LookAheadError, NotFoundError
from app.data.timeutil import describe_time

ErrorCode = Literal[
    "invalid_request",
    "unknown_ticker",
    "unknown_series",
    "prices_restricted",
    "not_found",
    "method_not_allowed",
    "internal_error",
]

INTERNAL_ERROR_MESSAGE = (
    "Something went wrong on our side. Try again later, and tell the team if it keeps "
    "happening."
)


class ErrorDetail(BaseModel):
    """One invalid field of a request."""

    field: str
    message: str


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    details: list[ErrorDetail]


class ErrorResponse(BaseModel):
    """The body of every error response."""

    error: ErrorBody


class ApiError(Exception):
    """An error the API answers with its own status, code, and message."""

    def __init__(self, status: int, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_response(
    status: int,
    code: ErrorCode,
    message: str,
    details: Sequence[ErrorDetail] = (),
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """A response with the contract's error body."""
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=list(details))
    )
    return JSONResponse(
        status_code=status, content=body.model_dump(mode="json"), headers=headers
    )


# Where a request parameter came from, the first part of a validation error's location.
_PARAMETER_SOURCES = {"query", "path", "header", "cookie", "body"}


def _invalid_field(error: Mapping[str, Any]) -> ErrorDetail:
    """One of a RequestValidationError's errors, as a field and a readable message."""
    location = [str(part) for part in error.get("loc", ())]
    if location and location[0] in _PARAMETER_SOURCES:
        location = location[1:]
    field = ".".join(location) or "request"
    return ErrorDetail(field=field, message=_explain(field, error))


def _explain(field: str, error: Mapping[str, Any]) -> str:
    kind, context = str(error.get("type")), error.get("ctx") or {}
    match kind:
        case "missing":
            return f"{field} is required."
        case "literal_error":
            return f"{field} must be {context['expected']}."
        case "greater_than_equal":
            return f"{field} must be at least {context['ge']}."
        case "less_than_equal":
            return f"{field} must be at most {context['le']}."
        case "int_parsing" | "int_from_float":
            return f"{field} must be a whole number."
        case "bool_parsing":
            return f"{field} must be true or false."
        case "value_error":
            # Our own sentences, such as as_of's. Pydantic prefixes a raised ValueError's.
            return str(error["msg"]).removeprefix("Value error, ")
    if kind.startswith("date"):
        return f"{field} must be a date such as 2020-04-01."
    return f"{field} is invalid: {str(error['msg']).rstrip('.')}."


async def _invalid_request(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    details = [_invalid_field(item) for item in error.errors()]
    message = " ".join(d.message for d in details) or "The request isn't valid."
    return error_response(422, "invalid_request", message, details)


async def _not_found(request: Request, error: NotFoundError) -> JSONResponse:
    ident = error.ident.strip().upper()
    if error.kind == "series":
        return error_response(
            404, "unknown_series", f"{ident} isn't a series in our catalog."
        )
    if error.kind == "ticker":
        message = f"No security in our data used the ticker {ident}"
        if error.knowledge_time is not None:
            message += f" as of {describe_time(error.knowledge_time)}"
        return error_response(404, "unknown_ticker", f"{message}.")
    return error_response(404, "not_found", f"We have no {error.kind} {ident}.")


async def _not_known_yet(request: Request, error: LookAheadError) -> JSONResponse:
    body = DataResponse[None](
        knowledge_time=error.knowledge_time,
        data_version=error.data_version,
        data=None,
        reason=str(error),
    )
    return JSONResponse(status_code=200, content=body.model_dump(mode="json"))


async def _api_error(request: Request, error: ApiError) -> JSONResponse:
    return error_response(error.status, error.code, error.message)


async def _http_error(request: Request, error: HTTPException) -> JSONResponse:
    """Starlette's own errors, such as a path no route matches."""
    path = request.url.path
    if error.status_code == 404:
        code, message = "not_found", f"There's no endpoint at {path}."
    elif error.status_code == 405:
        code, message = "method_not_allowed", f"{path} doesn't accept {request.method}."
    else:
        code, message = "invalid_request", str(error.detail)
    return error_response(error.status_code, code, message, headers=error.headers)


def add_error_handlers(app: FastAPI) -> None:
    """Answer every handled error with the contract's body.

    Unhandled exceptions are `InternalErrorMiddleware`'s job, which `create_app` adds.
    """
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(LookAheadError, _not_known_yet)
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(HTTPException, _http_error)


class InternalErrorMiddleware:
    """Answers an unhandled exception with the contract's 500 body, then re-raises it.

    Add it before CORSMiddleware, so that CORS wraps it and the browser can read the
    body. An exception handler for `Exception` would run outside CORS, and its 500 would
    reach the page as a network error. Re-raising lets the server log the traceback;
    Starlette sees that the response has started and doesn't send another.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_and_track(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_and_track)
        except Exception:
            if not started:
                response = error_response(500, "internal_error", INTERNAL_ERROR_MESSAGE)
                await response(scope, receive, send)
            raise
