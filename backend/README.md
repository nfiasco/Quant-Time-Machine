# Quant Time Machine — Backend

The Quant Time Machine API, built with [FastAPI](https://fastapi.tiangolo.com). It will serve point-in-time data and run backtests. So far it has the foundations of the point-in-time data layer and the conventions every `/v1` endpoint follows:

- the store and its writer;
- `PointInTimeView`;
- the NYSE calendar;
- the ingestion client and CLI.

Macro vintages from ALFRED (S4.2–S4.4), company identity (S5.2), and raw daily prices (S6.2, S6.3) are in. Filings and the endpoints come next (S5.3, S5.4, S8.2).

## Getting started

Install [uv](https://docs.astral.sh/uv/) once (`brew install uv` on macOS; see the uv docs for Windows and Linux). uv installs the correct Python version (pinned in [`.python-version`](.python-version)) and all dependencies:

```bash
uv sync             # create .venv/ and install dependencies from uv.lock
uv run fastapi dev  # start the dev server with auto-reload
```

Then open:

- http://localhost:8000/health returns `{"status": "ok"}`
- http://localhost:8000/v1/knowledge-time?as_of=2020-06-05 returns `{"knowledge_time": "2020-06-05T13:30:00Z", "data_version": null}`
- http://localhost:8000/docs is the interactive API docs (Swagger UI), generated automatically

`uv run <command>` runs a command inside the project's virtual environment, so you don't need to activate it first.

## Configuration

Settings and API keys load through one typed module, [`app/config.py`](app/config.py) (built on [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)). Copy [`.env.example`](.env.example) to `.env` and fill it in. `.env` is git-ignored, and real environment variables take precedence over it.

| Variable         | Needed for                                    | Notes                                                                                                                      |
| ---------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `FRED_API_KEY`   | Downloading economic data from FRED/ALFRED    | Free: sign in at [fredaccount.stlouisfed.org](https://fredaccount.stlouisfed.org/apikeys) and request a key                |
| `SEC_USER_AGENT` | Downloading filings from SEC EDGAR            | Your name or the project's plus a contact email; SEC refuses requests without one. Validated to contain an email address. |
| `TIINGO_API_KEY` | Downloading daily prices from Tiingo (D2)     | Free: create a Tiingo account and copy the token from [its API token page](https://www.tiingo.com/account/api/token)      |
| `DATA_DIR`       | Where downloads and the local store live      | Default `data/` (that is, `backend/data/`, git-ignored). Relative paths are resolved from `backend/`.                      |
| `CORS_ORIGINS`   | Browser access to the API (CORS)              | Exact origins, comma-separated, no trailing slash. Default `http://localhost:3000`; add the deployed site.                 |

In code, call `get_settings()` from `app.config`. API keys are `SecretStr` values, so they never show up in logs; use `.get_secret_value()` where the real value is needed. The tests don't need any of these: they build `Settings(_env_file=None)` and use fixtures instead of live APIs.

## Tests and linting

```bash
uv run pytest               # run tests
uv run ruff check           # lint (add --fix to auto-fix)
uv run ruff format          # format code
```

CI runs `ruff check`, `ruff format --check`, and `pytest` on every pull request.

The tests read small committed tables from [`tests/fixtures/`](tests/fixtures/), loaded into a temporary store; that folder's README explains the format.

Tests that call real APIs are marked `network`. They're skipped by default, so CI never runs them. To run them, put keys in `.env` and use `uv run pytest -m network`. Each makes one request, and Tiingo's counts against its limit of 50 an hour.

## Managing dependencies

```bash
uv add <package>          # runtime dependency (e.g. pandas)
uv add --dev <package>    # development-only tool (tests, linting)
```

These commands update `pyproject.toml` and `uv.lock`. Commit both files so everyone (and CI) installs the exact same versions.

## Project structure

```
backend/
├── app/
│   ├── main.py         # Creates the FastAPI app and registers routers
│   ├── config.py       # Typed settings: API keys and paths from the environment or .env
│   ├── api/            # HTTP route handlers (thin; they call into data/ and backtest/)
│   │   ├── health.py   # GET /health
│   │   ├── v1.py       # The /v1 router
│   │   ├── conventions.py    # as_of parsing, response envelope, error handlers
│   │   └── knowledge_time.py # GET /v1/knowledge-time
│   ├── data/           # Point-in-time data layer (see below)
│   └── backtest/       # Backtesting engine (placeholder)
├── spikes/             # Sprint 1 experiments behind the data and storage decisions (not app code)
├── tests/              # pytest tests, plus fixtures/ (small committed tables)
├── data/               # DATA_DIR: downloads and the local store (git-ignored; created when needed)
├── .env.example        # Template for .env (copy it; never commit .env)
├── pyproject.toml      # Project metadata, dependencies, and tool settings
└── uv.lock             # Locked dependency versions (generated by uv; commit it)
```

To add an endpoint, create a router module in `app/api/` (see `knowledge_time.py`) and include it in `app/api/v1.py`, so it's served under `/v1`.

## API conventions (`/v1`)

Every `/v1` endpoint follows [`app/api/conventions.py`](app/api/conventions.py) (S8.1):

- **`as_of` is required.** It's the knowledge time: the moment to answer as of. The rules are in [`doc/time-model.md`](../doc/time-model.md), rule 3.

  | `as_of`                | Means                                    | Instant used           |
  | ---------------------- | ---------------------------------------- | ---------------------- |
  | `2020-06-05`           | 09:30 ET that day, even on a weekend     | `2020-06-05T13:30:00Z` |
  | `2020-06-05T09:30`     | New York time                            | `2020-06-05T13:30:00Z` |
  | `2020-06-05T13:30:00Z` | Used as given (encode `+` as `%2B`)      | `2020-06-05T13:30:00Z` |

- **Every response echoes** `knowledge_time` (the exact instant used, in UTC) and `data_version` (`null` until data versions exist, S3.7).
- **Errors:**
  - 404 for an unknown ticker or series (raise `NotFoundError`);
  - 422 for invalid input;
  - 200 with `value: null` and a `reason` when nothing was known yet (raise `LookAheadError`).
- **CORS:** only the origins in `CORS_ORIGINS` may call the API from a browser.

## Point-in-time data layer

| Module | What it does |
| --- | --- |
| [`timeutil.py`](app/data/timeutil.py) | The market clock and `parse_knowledge_time` |
| [`calendar.py`](app/data/calendar.py) | The NYSE calendar: sessions, open and close times (with early closes), previous and next session, and the first trading day of a month (S3.5) |
| [`store.py`](app/data/store.py) | The Parquet store: `TableSpec` and `write_rows` (S3.4) |
| [`tables.py`](app/data/tables.py) | Every table in the store |
| [`view.py`](app/data/view.py) | `PointInTimeView`, the only way to read the store (S3.3) |
| [`records.py`](app/data/records.py) | What the view's reads return, with the field names of the API contract |
| [`raw_cache.py`](app/data/raw_cache.py) and [`http.py`](app/data/http.py) | Downloads, with rate limits, retries, and a cache of every response |
| [`ingest.py`](app/data/ingest.py) | The ingestion command |
| [`sources/`](app/data/sources/) | One ingester per source, with its config files |

**Store.** Each table is a folder of Parquet files under `DATA_DIR/store/<table>/`, defined by a `TableSpec` in `tables.py`:

- **Provenance.** Every row carries `source`, `source_ref`, `available_at`, `ingested_at` (in UTC), and `time_assumed`.
- **Append-only.** `write_rows` adds rows and never changes stored ones. A row whose key and `available_at` are already stored is skipped, so re-running ingestion adds nothing twice. A revision is a new row with a later `available_at`.
- **Rebuilding.** Changing how a table's `available_at` is computed means deleting `DATA_DIR/store/<table>/` and ingesting again from the raw cache.

**Reading.** Create a `PointInTimeView` for a knowledge time and call its read methods. They return only rows with `available_at` at or before that time, and log every row they read. Nothing else may open DuckDB or Parquet files, and a test enforces this.

| Read | Returns |
| --- | --- |
| `get_macro_as_of(series_id, period=None)` | A `MacroObservation`: the latest observation published by then, or the given period's latest version; `None` if nothing was published yet (S4.4) |
| `get_macro_series_as_of(series_id, start=None, end=None)` | The whole series as it looked then, each observation at its latest version, oldest first (S4.4) |
| `resolve_ticker(ticker)` | The `Security` that used the ticker then: FB in 2020 is Facebook, and WB is Wachovia in 2005 but Weibo in 2020 (S5.2) |
| `get_price_as_of(ticker, session=None)` | A `PriceBar`: the latest raw daily bar whose session had closed by then, so at 09:30 ET a bar from the day before; or one session's bar, raising `LookAheadError` if that session hadn't closed yet (S6.3) |
| `get_price_history_as_of(ticker, lookback)` | The last `lookback` bars known then, oldest first, for signals (S6.3) |

```python
from app.data.timeutil import parse_knowledge_time
from app.data.view import PointInTimeView

with PointInTimeView(parse_knowledge_time("2020-06-05")) as view:  # 09:30 ET
    view.get_macro_as_of("UNRATE").value  # 13.3, May's first print from 08:30 that day
```

A series outside the catalog in `alfred_series.toml`, or a ticker no security in our data used at the time, raises `NotFoundError`, which the API answers with 404.

## Ingestion

```bash
uv run python -m app.data.ingest <source> [--refresh]   # source: fred, sec, or tiingo
```

Each source's ingester lives in [`app/data/sources/`](app/data/sources/) and is listed in `INGESTERS` in [`app/data/ingest.py`](app/data/ingest.py).

| Source | Ingester | What it loads |
| --- | --- | --- |
| `fred` | [`sources/alfred.py`](app/data/sources/alfred.py) | Every vintage of the series in [`sources/alfred_series.toml`](app/data/sources/alfred_series.toml), UNRATE first, into `macro_observations` (S4.2). Each request asks for ALFRED's whole real-time range, because FRED's defaults return today's revised values. |
| `sec` | [`sources/securities.py`](app/data/sources/securities.py) | The curated ticker history in [`sources/securities.toml`](app/data/sources/securities.toml) into `securities`, and a snapshot of SEC's ticker file into `sec_tickers` (S5.2). It warns when a curated security's current ticker isn't in SEC's file. |
| `tiingo` | [`sources/tiingo.py`](app/data/sources/tiingo.py), through [`sources/prices.py`](app/data/sources/prices.py) | Raw daily bars for the starter set, SPY included, into `price_bars`, and the splits and dividends they report into `corporate_actions` (S6.2). A first run loads each security from 2005. Later runs ask only for sessions after its last stored bar, through the last one Tiingo has settled (20:00 ET), and log any session that comes back without a bar. Adjusted prices are never stored. |

Each vintage counts as known on its date at its release's time, New York time: 08:30 for BLS's and BEA's releases, 16:15 for the Fed's H.15 (S4.3). The times and their sources are in `alfred_series.toml`, and [`doc/time-model.md`](../doc/time-model.md) (rule 7) summarizes them. A release whose time isn't known (`time = "unknown"`) makes its vintages known at the end of their date, flagged `time_assumed`.

To add a macro series, add it to `alfred_series.toml` with FRED's metadata and its release, then run `ingest fred` again. A new release needs its time and a source for it.

**Raw cache.** Every response is saved as it arrived under `DATA_DIR/raw/<source>/`, with a metadata file: the URL without secrets, the status, and the fetch time. A re-run answers from the cache, and `--refresh` downloads again. API keys are never written to disk or to the command's log. Every source answers in JSON, so a page that isn't JSON (FRED serves an HTML page with status 200 while it's down for maintenance) counts as a failed request and isn't cached.

**Rate limits.** The client stays within each source's limits and retries failures with backoff:

| Source | Limit |
| --- | --- |
| SEC EDGAR | 10 requests per second, with `SEC_USER_AGENT` |
| FRED | 120 requests per minute |
| Tiingo | 50 per hour and 1,000 per day (free plan; also 500 symbols per month) |

When a limit would mean waiting more than a minute, the command stops and says when to run it again. The re-run reuses the cache, so it picks up where it stopped.

## Spikes

[`spikes/`](spikes/) holds the Sprint 1 experiments: the ALFRED, EDGAR, and price-source explorations and the storage benchmark. Each is a self-contained script with its own pinned dependencies, run with `uv run spikes/<name>.py`. See [`spikes/README.md`](spikes/README.md) for what each needs. Their findings are written up in [`doc/data-sources.md`](../doc/data-sources.md) and [`doc/storage.md`](../doc/storage.md).

## Design principles (draft)

- **No look-ahead.** Every data record carries the time it became publicly available, and all reads go through "as of" queries, so a simulation can only see what was known on its simulated date. The rules are in [`doc/time-model.md`](../doc/time-model.md).
- **Deterministic calculations.** The same inputs always produce the same results. Any future AI assistant helps plan experiments, while plain, tested code does the calculations.
