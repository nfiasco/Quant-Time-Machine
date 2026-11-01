# Test fixtures

Small, committed tables that the tests load into a temporary point-in-time store, so CI checks point-in-time behavior with no network and no API keys (S3.6).

## Format

- **One CSV per table.** `<table>.csv` loads into the table of that name in [`app/data/tables.py`](../../app/data/tables.py), or into a test-only table in [`fixture_loader.py`](../fixture_loader.py). A file with no matching table fails the tests.
- **Columns.** The header lists the table's own columns, then `source`, `source_ref`, `available_at`, and `time_assumed`. Leave out `ingested_at`: the loader stamps it, as ingestion does, always with 2026-10-19T12:00Z, so the store's data version never changes.
- **Timestamps carry an offset**, preferably `Z` for UTC, as in `2020-06-05T12:30:00Z`. A timestamp without one fails to load (doc/time-model.md, rule 1).
- **Other values.** Dates are `YYYY-MM-DD`, booleans are `true` or `false`, and an empty cell is a missing value.

## Rules

- **Prices are made up.** Tiingo's terms don't allow sharing its data (decision D2), so price fixtures use invented values, never copies.
- **FRED and SEC values may be real.** They're public. Put the vintage, URL, or accession number in `source_ref`.
- **Every file has a canary row** with `available_at` in 2099 or later. No query at a realistic knowledge time may return it, and [`test_view.py`](../test_view.py) checks this for every table. The loader refuses a file without one.
- **Keep files small:** a few rows per case, each there for a test.
- **`securities.csv` copies the whole history of each security it lists** from [`app/data/sources/securities.toml`](../../app/data/sources/securities.toml): the M2 ticker set, plus Tesla for the universe tests. A test fails if the two drift apart.
- **`universe_members.csv` copies the spells it lists** from [`app/data/sources/universes.toml`](../../app/data/sources/universes.toml): Apple, Meta, Tesla (rule 8's golden test), and Twitter, which left. A test checks it the same way.
- **`xbrl_facts.csv` holds real company facts from SEC, timed as ingestion times them**: each at its filing's acceptance time in `filings.csv`, or at the end of its filed date, flagged, when its filing isn't there. A test checks it.

## Using them

In a test, the `fixture_store` fixture is a temporary store holding every file here, and `store_dir` is an empty one. Both are defined in [`conftest.py`](../conftest.py). The fixture store is one data version, `20261019T120000Z` (`FIXTURE_DATA_VERSION`), which the API tests and the `/docs` examples echo.

## Network tests

Tests that call real APIs are marked `@pytest.mark.network` and need keys in `backend/.env`. They're skipped by default, so CI never runs them. Run them with `uv run pytest -m network`.
