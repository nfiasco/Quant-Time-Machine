"""Tiingo's end-of-day prices, our daily price source (decision D2; S6.2).

`uv run python -m app.data.ingest tiingo` loads new bars for the starter set, SPY
included, through sources/prices.py. Each bar from
`tiingo/daily/<symbol>/prices?startDate=...&endDate=...` has raw fields (open, high,
low, close, volume), adjusted ones (adjOpen, adjClose, and so on), the dividend paid
(`divCash`), and the split factor (`splitFactor`). Only the raw fields, the dividend,
and the split factor are read: adjusted prices change every time a later split or
dividend happens, so they'd carry the future into the past. They stay only in the raw
cache, as Tiingo sent them.

Tiingo's free plan is for internal use only (doc/data-sources.md, D2), and allows 50
requests an hour; a run makes one per security that has new sessions.
"""

from collections.abc import Mapping
from datetime import UTC, date, datetime, time
from typing import Any

from app.data.http import SourceClient
from app.data.sources import IngestContext, securities
from app.data.sources.prices import SourceBar, ingest_prices


class TiingoPriceSource:
    """Raw daily bars from Tiingo's end-of-day API."""

    name = "tiingo"
    settled_by = time(20, 0)
    """Tiingo has most prices by 17:30 ET and makes corrections until 20:00 ET."""

    def __init__(self, client: SourceClient) -> None:
        self._client = client

    def fetch_bars(self, symbol: str, start: date, end: date) -> list[SourceBar]:
        response = self._client.get(
            f"tiingo/daily/{symbol}/prices",
            {"startDate": start.isoformat(), "endDate": end.isoformat()},
        )
        return [_raw_bar(record) for record in response.json()]


def _raw_bar(record: Mapping[str, Any]) -> SourceBar:
    """A Tiingo bar's raw prices, dividend, and split factor; never its adjusted ones."""
    volume = record.get("volume")
    return SourceBar(
        # Tiingo dates a bar by its session at midnight UTC: "2020-06-04T00:00:00.000Z".
        session_date=date.fromisoformat(record["date"][:10]),
        open=record.get("open"),
        high=record.get("high"),
        low=record.get("low"),
        close=record.get("close"),
        volume=None if volume is None else int(volume),
        dividend=record.get("divCash") or 0.0,
        split_factor=record.get("splitFactor") or 1.0,
    )


def ingest(context: IngestContext, now: datetime | None = None) -> None:
    """Load the starter set's new bars from Tiingo.

    It also writes the curated securities, so prices can be read by ticker even if
    `ingest sec` hasn't run yet.
    """
    securities.write_curated(context.store)
    ingest_prices(
        context.store,
        TiingoPriceSource(context.client),
        securities.CURATED.starter_set,
        now=datetime.now(UTC) if now is None else now,
    )
