"""Errors that data reads raise and the API turns into responses (see app.api.conventions)."""

from datetime import datetime


class LookAheadError(Exception):
    """A read asked for something that wasn't known yet at the knowledge time.

    For example, the June 5, 2020 close at 09:30 ET that morning. The API answers with
    200 and `value: null`, using this message as the reason, so it carries the knowledge
    time and data version that response echoes.
    """

    def __init__(
        self, message: str, *, knowledge_time: datetime, data_version: str | None = None
    ) -> None:
        super().__init__(message)
        self.knowledge_time = knowledge_time
        self.data_version = data_version


class NotFoundError(LookupError):
    """An unknown ticker, series, or other identifier. The API answers with 404.

    `knowledge_time` is set when the answer depends on it: a ticker can belong to no one
    at one time and to a security at another.
    """

    def __init__(
        self, kind: str, ident: str, *, knowledge_time: datetime | None = None
    ) -> None:
        super().__init__(f"unknown {kind}: {ident}")
        self.kind = kind
        self.ident = ident
        self.knowledge_time = knowledge_time
