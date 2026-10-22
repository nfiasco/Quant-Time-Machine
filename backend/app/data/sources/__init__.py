"""The ingesters: one module per source, each downloading through the raw cache and
writing normalized rows to the point-in-time store.

Each module has an `ingest(context)` function, and app/data/ingest.py maps the command's
source names to them:

- `alfred`: every vintage of the starter macro series (`ingest fred`, S4.2)
- `securities`: who used which ticker when, curated and from SEC (`ingest sec`, S5.2)
- `prices` and `tiingo`: raw daily bars, splits, and dividends (`ingest tiingo`, S6.2)
"""

from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.data.http import SourceClient


@dataclass(frozen=True)
class IngestContext:
    """What an ingester works with."""

    settings: Settings
    client: SourceClient
    """Fetches from the ingester's source, through the raw cache."""
    store: Path
    """The point-in-time store, for `write_rows`."""


class IngestError(Exception):
    """Something ingestion can't safely write, such as a config file that no longer
    matches its source. The command prints the message and exits 1."""
