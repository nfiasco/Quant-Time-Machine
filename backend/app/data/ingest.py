"""Run ingestion for one source (S3.4). From backend/:

    uv run python -m app.data.ingest <source> [--refresh]

Downloads go through the source's rate limits into the raw cache (DATA_DIR/raw/), and
normalized rows go into the point-in-time store (DATA_DIR/store/). A re-run reuses
cached responses, so it makes no requests for what it already has; `--refresh`
downloads everything again. Keys and the SEC User-Agent come from backend/.env.
"""

import argparse
import logging
import sys
from collections.abc import Callable, Sequence

from app.config import get_settings
from app.data.http import (
    SOURCES,
    FetchError,
    MissingSettingError,
    RateLimitExceeded,
    client_for,
)
from app.data.sources import IngestContext, IngestError, alfred, edgar, tiingo
from app.data.store import store_dir

__all__ = ["INGESTERS", "IngestContext", "main"]

INGESTERS: dict[str, Callable[[IngestContext], None]] = {
    "fred": alfred.ingest,
    "sec": edgar.ingest,
    "tiingo": tiingo.ingest,
}
"""Each source's ingester, by source name.

The map is written out here rather than filled in by each source module when it's
imported: `python -m app.data.ingest` runs this file as `__main__`, so a module that
imported `app.data.ingest` to register itself would fill a second copy of the map."""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.data.ingest",
        description="Download a source into the raw cache and the point-in-time store.",
    )
    parser.add_argument("source", choices=sorted(SOURCES), help="the source to ingest")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="download again instead of reusing cached responses",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    # httpx2 logs each request's full URL at INFO, and FRED's URLs carry the API key.
    for library in ("httpx2", "httpcore2"):
        logging.getLogger(library).setLevel(logging.WARNING)

    ingester = INGESTERS.get(args.source)
    if ingester is None:
        print(f"No ingester for {args.source} yet.", file=sys.stderr)
        return 2

    settings = get_settings()
    try:
        with client_for(args.source, settings, refresh=args.refresh) as client:
            ingester(IngestContext(settings, client, store_dir(settings.data_dir)))
    except MissingSettingError as error:
        print(error, file=sys.stderr)
        return 2
    except RateLimitExceeded as error:
        print(
            f"{error}. Run the same command again after that: cached responses are "
            "reused, so it picks up where it stopped.",
            file=sys.stderr,
        )
        return 1
    except (FetchError, IngestError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
