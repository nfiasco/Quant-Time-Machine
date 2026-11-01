# Quant Time Machine — Backend

The Quant Time Machine API, built with [FastAPI](https://fastapi.tiangolo.com). It serves point-in-time data and will run backtests. So far it has:

- the point-in-time data layer: the store and its writer, `PointInTimeView`, and the NYSE calendar;
- the ingestion client and CLI;
- the `/v1` as-of endpoints for macro series, prices, and filings, with their conventions.

Three sources are in, each ingested and readable as of any moment:

- macro vintages from ALFRED (S4.2–S4.4);
- raw daily prices from Tiingo (S6.2, S6.3);
- filing histories from SEC EDGAR (S5.3, S5.4), with the XBRL facts reported in them (S5.5).

Company identity ties tickers to securities over time (S5.2), universe v1 says which companies were eligible when (S6.5), and the as-of endpoints serve the data (S8.2). Every response says which [data version](#data-versions) it read (S3.7).

## Getting started

Install [uv](https://docs.astral.sh/uv/) once (`brew install uv` on macOS; see the uv docs for Windows and Linux). uv installs the correct Python version (pinned in [`.python-version`](.python-version)) and all dependencies:

```bash
uv sync             # create .venv/ and install dependencies from uv.lock
uv run fastapi dev  # start the dev server with auto-reload
```

Then open:

- http://localhost:8000/health returns `{"status": "ok"}`
- http://localhost:8000/v1/knowledge-time?as_of=2020-06-05 returns `{"knowledge_time": "2020-06-05T09:30:00-04:00", "data_version": "20261101T143005Z"}`, with your store's newest [data version](#data-versions), or `null` before your first ingestion run
- http://localhost:8000/docs is the interactive API docs (Swagger UI), with an example for every endpoint

The data endpoints need a local store. With keys in `.env`, [ingest](#ingestion) the three sources once. That takes about two minutes, plus a Tiingo rerun an hour later, because universe v1's first price load is one request over Tiingo's hourly limit. Then http://localhost:8000/v1/macro/UNRATE?as_of=2020-06-05 returns May 2020's first print, 13.3%.

`uv run <command>` runs a command inside the project's virtual environment, so you don't need to activate it first.

## Configuration

Settings and API keys load through one typed module, [`app/config.py`](app/config.py) (built on [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)). Copy [`.env.example`](.env.example) to `.env` and fill it in. `.env` is git-ignored, and real environment variables take precedence over it.

| Variable           | Needed for                                    | Notes                                                                                                                      |
| ------------------ | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `FRED_API_KEY`     | Downloading economic data from FRED/ALFRED    | Free: sign in at [fredaccount.stlouisfed.org](https://fredaccount.stlouisfed.org/apikeys) and request a key                |
| `SEC_USER_AGENT`   | Downloading filings from SEC EDGAR            | Your name or the project's plus a contact email; SEC refuses requests without one. Validated to contain an email address. |
| `TIINGO_API_KEY`   | Downloading daily prices from Tiingo (D2)     | Free: create a Tiingo account and copy the token from [its API token page](https://www.tiingo.com/account/api/token)      |
| `DATA_DIR`         | Where downloads and the local store live      | Default `data/` (that is, `backend/data/`, git-ignored). Relative paths are resolved from `backend/`.                      |
| `CORS_ORIGINS`     | Browser access to the API (CORS)              | Exact origins, comma-separated, no trailing slash. Default `http://localhost:3000`; add the deployed site.                 |
| `SERVE_RAW_PRICES` | `GET /v1/prices` answering at all             | Default `false`, so the endpoint answers 403. Tiingo's prices are internal use only (D2): set `true` on your own machine, never on a deployment others can reach. |

In code, call `get_settings()` from `app.config`. API keys are `SecretStr` values, so they never show up in logs; use `.get_secret_value()` where the real value is needed. Route handlers don't call `get_settings()`. They read the settings the app was built with, through the `AppSettings` dependency, so a test can build an app with its own settings: `create_app(Settings(_env_file=None, data_dir=...))`. The tests don't need any keys: they use fixtures instead of live APIs.

## Tests and linting

```bash
uv run pytest               # run tests
uv run ruff check           # lint (add --fix to auto-fix)
uv run ruff format          # format code
```

CI runs `ruff check`, `ruff format --check`, and `pytest` on every pull request.

The tests read small committed tables from [`tests/fixtures/`](tests/fixtures/), loaded into a temporary store; that folder's README explains the format. The `client` fixture in [`tests/conftest.py`](tests/conftest.py) is the API reading that store.

Tests that call real APIs are marked `network`. They're skipped by default, so CI never runs them. To run them, put keys in `.env` and use `uv run pytest -m network`. There are eight, each making a request or a few. Two call Tiingo's API and count against its limit of 50 an hour; a third downloads Tiingo's public ticker list, which doesn't.

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
│   │   ├── conventions.py    # as_of, the per-request view, the response envelope
│   │   ├── errors.py         # The error body and the handlers that produce it
│   │   ├── examples.py       # The example responses shown in /docs
│   │   ├── knowledge_time.py # GET /v1/knowledge-time
│   │   ├── macro.py          # GET /v1/macro/{series_id}
│   │   ├── prices.py         # GET /v1/prices/{ticker}
│   │   └── filings.py        # GET /v1/filings/{ticker} and /latest
│   ├── data/           # Point-in-time data layer (see below)
│   └── backtest/       # Backtesting engine (placeholder)
├── spikes/             # Experiments behind the data, storage, and hosting decisions (not app code)
├── tests/              # pytest tests, plus fixtures/ (small committed tables)
├── data/               # DATA_DIR: downloads and the local store (git-ignored; created when needed)
├── Dockerfile          # The deployed image (S1.6); fly.toml configures Fly.io
├── .env.example        # Template for .env (copy it; never commit .env)
├── pyproject.toml      # Project metadata, dependencies, and tool settings
└── uv.lock             # Locked dependency versions (generated by uv; commit it)
```

## API conventions (`/v1`)

Every `/v1` endpoint follows [`app/api/conventions.py`](app/api/conventions.py) and the contract in [`doc/api-v1.md`](../doc/api-v1.md) (S8.1):

- **`as_of` is required.** It's the knowledge time: the moment to answer as of. The rules are in [`doc/time-model.md`](../doc/time-model.md), rule 3.

  | `as_of`                | Means                                    | Echoed as `knowledge_time`  |
  | ---------------------- | ---------------------------------------- | --------------------------- |
  | `2020-06-05`           | 09:30 ET that day, even on a weekend     | `2020-06-05T09:30:00-04:00` |
  | `2020-06-05T09:30`     | New York time                            | `2020-06-05T09:30:00-04:00` |
  | `2020-06-05T13:30:00Z` | Used as given (encode `+` as `%2B`)      | `2020-06-05T09:30:00-04:00` |
  | `2020-03-08T02:30`     | Never happened (clocks jumped an hour)   | 422; add an offset          |

- **Every timestamp in a response** is New York time with its offset (D12), and every response echoes `knowledge_time` and `data_version`: the store's newest [data version](#data-versions), which every read in the request is pinned to, or `null` if the store has none yet.
- **Data endpoints answer with a `DataResponse`.** `data` is the answer, or `null` (`[]` for a list) when nothing was known yet. In that case `reason` is a sentence the page can show, and it's still a 200.
- **Errors** share one body, `{"error": {"code", "message", "details"}}` ([`app/api/errors.py`](app/api/errors.py)):

  | Status | `code` | When |
  | --- | --- | --- |
  | 422 | `invalid_request` | A missing or invalid parameter; `details` names each one |
  | 404 | `unknown_ticker`, `unknown_series` | Raise `NotFoundError` |
  | 403 | `prices_restricted` | `SERVE_RAW_PRICES` is off |
  | 404, 405 | `not_found`, `method_not_allowed` | No such path or method |
  | 500 | `internal_error` | A bug; the message is generic |

- **CORS:** only the origins in `CORS_ORIGINS` may call the API from a browser. Errors carry the CORS headers too, so a page can read them.

**Adding an endpoint:**

1. Create a router module in `app/api/` (see `macro.py`), and include it in `app/api/v1.py`, so it's served under `/v1`.
2. Take `view: View` to read the store: one `PointInTimeView` per request, bound to `as_of`.
3. Return a named subclass of `DataResponse`, whose `data` is a model built on `Provenance`.
4. Add its examples to `app/api/examples.py`, each labeled with the request that produces it. `tests/test_api_examples.py` replays every one against the fixtures.

## Endpoints

| Endpoint | Answers with | Reads |
| --- | --- | --- |
| `GET /v1/knowledge-time?as_of` | The exact instant an `as_of` means, and the data version the data endpoints read now | `latest_data_version` |
| `GET /v1/macro/{series_id}?as_of&period` | A series' latest observation as published then, or one period's latest version | `get_macro_as_of` |
| `GET /v1/prices/{ticker}?as_of` | The latest daily bar whose session had closed; 403 unless `SERVE_RAW_PRICES` is on | `get_price_as_of` |
| `GET /v1/filings/{ticker}/latest?as_of&form&include_amendments` | The latest 10-K, 10-Q, or 8-K accepted by EDGAR then | `get_latest_filing_as_of` |
| `GET /v1/filings/{ticker}?as_of&form&include_amendments&limit` | The filings accepted by then, newest first | `list_filings_as_of` |

`/revisions`, `/fundamentals`, and `/snapshot` follow in Sprint 3 ([`doc/api-v1.md`](../doc/api-v1.md#coming-after-m2)).

## Point-in-time data layer

| Module | What it does |
| --- | --- |
| [`timeutil.py`](app/data/timeutil.py) | The market clock, `parse_knowledge_time`, and `describe_time` ("June 5, 2020, 9:30 AM ET") |
| [`calendar.py`](app/data/calendar.py) | The NYSE calendar: sessions, open and close times (with early closes), previous and next session, and the first trading day of a month (S3.5) |
| [`store.py`](app/data/store.py) | The Parquet store: `TableSpec` and `write_rows` (S3.4) |
| [`versions.py`](app/data/versions.py) | [Data versions](#data-versions): the manifest each ingestion run writes, and what a pinned view reads (S3.7) |
| [`tables.py`](app/data/tables.py) | Every table in the store |
| [`view.py`](app/data/view.py) | `PointInTimeView`, the only way to read the store (S3.3) |
| [`records.py`](app/data/records.py) | What the view's reads return, with the field names of the API contract |
| [`fundamentals.py`](app/data/fundamentals.py) | Standard metrics from XBRL facts: each concept's latest value per period, the concept order, and coverage (S5.6) |
| [`coverage.py`](app/data/coverage.py) | The coverage report for the standard metrics (S5.6) |
| [`raw_cache.py`](app/data/raw_cache.py) and [`http.py`](app/data/http.py) | Downloads, with rate limits, retries, and a cache of every response |
| [`ingest.py`](app/data/ingest.py) | The ingestion command |
| [`sources/`](app/data/sources/) | One ingester per source, with its config files |

**Store.** Each table is a folder of Parquet files under `DATA_DIR/store/<table>/`, defined by a `TableSpec` in `tables.py` (see [Data layout](#data-layout)):

- **Provenance.** Every row carries `source`, `source_ref`, `available_at`, `ingested_at` (in UTC), and `time_assumed`.
- **Append-only.** `write_rows` adds rows and never changes stored ones. A row whose key and `available_at` are already stored is skipped, so re-running ingestion adds nothing twice. A revision is a new row with a later `available_at`.
- **Rebuilding.** Changing how a table's `available_at` is computed means deleting `DATA_DIR/store/<table>/` and ingesting again from the raw cache. That breaks every [data version](#data-versions) that lists the deleted files: a view pinned to one raises `DataVersionError` rather than answer from different data. Until the next ingestion run writes a new version, the API answers 500.

**Reading.** Create a `PointInTimeView` for a knowledge time and call its read methods. They return only rows with `available_at` at or before that time, and log every row they read. Nothing else may open DuckDB or Parquet files, and a test enforces this.

| Read | Returns |
| --- | --- |
| `get_macro_as_of(series_id, period=None)` | A `MacroObservation`: the latest observation published by then, or the given period's latest version; `None` if nothing was published yet (S4.4) |
| `get_macro_series_as_of(series_id, start=None, end=None)` | The whole series as it looked then, each observation at its latest version, oldest first (S4.4) |
| `resolve_ticker(ticker)` | The `Security` that used the ticker then: FB in 2020 is Facebook, and WB is Wachovia in 2005 but Weibo in 2020 (S5.2) |
| `get_price_as_of(ticker, session=None)` | A `PriceBar`: the latest raw daily bar whose session had closed by then, so at 09:30 ET a bar from the day before; or one session's bar, raising `LookAheadError` if that session hadn't closed yet (S6.3) |
| `get_price_history_as_of(ticker, lookback)` | The last `lookback` bars known then, oldest first, for signals (S6.3) |
| `get_latest_filing_as_of(ticker, form="10-Q", include_amendments=False)` | A `Filing`: the latest of a form family EDGAR had accepted by then, counted from its acceptance time, never its filing date (S5.4) |
| `list_filings_as_of(ticker, forms=("10-K", "10-Q", "8-K"), include_amendments=False, limit=100)` | The filings accepted by then, newest first, across every CIK the security had (S5.4) |
| `universe_as_of(name)` | The `UniverseMember`s of a universe in [`universes.toml`](app/data/sources/universes.toml), such as `starter_large_caps`, each with its ticker, name, and CIK then. A company counts from 00:00 ET on the effective date it joined until the date it left: Tesla is in from December 21, 2020 (S6.5) |
| `fundamentals_coverage(universe, metric)` | For every company in the universe by then, those that left included: how many of its 10-Qs and 10-Ks reported one of the metric's concepts for their own period, which concepts they used, and the periods none covered (S5.6) |

```python
from app.data.timeutil import parse_knowledge_time
from app.data.view import PointInTimeView

with PointInTimeView(parse_knowledge_time("2020-06-05")) as view:  # 09:30 ET
    view.get_macro_as_of("UNRATE").value  # 13.3, May's first print from 08:30 that day
```

A series outside the catalog in `alfred_series.toml`, or a ticker no security in our data used at the time, raises `NotFoundError`, which the API answers with 404.

## Data versions

A data version is the store as one finished ingestion run left it, so a saved run can replay on exactly the data it saw (S3.7, [`app/data/versions.py`](app/data/versions.py)).

- **The manifest.** When an ingestion command finishes, it writes `DATA_DIR/store/_versions/<data_version>.json`. That file lists every Parquet file in the store, with its size and SHA-256 hash, the rows per table and per source, and the latest `ingested_at`.
- **The name** is when the version was cut, in UTC, such as `20261101T143005Z`. Names only increase, so the newest sorts last.
- **No partial or duplicate versions.** A run that fails or stops at a rate limit writes no manifest, and a run that adds nothing keeps the newest version.
- **Pinning.** A view pinned to a version reads only that version's files, and only rows ingested by then, so data added later never changes its answers:

  ```python
  with PointInTimeView(
      parse_knowledge_time("2020-06-05"), data_version="20261101T143005Z"
  ) as view:
      view.get_macro_as_of("UNRATE")  # the same answer, however much is ingested later
  ```

  A pinned view first checks that every file the version lists is still there with the same size, and the first time in a process, the same hash. If one is missing or changed, it raises `DataVersionError` instead of answering from different data. Without `data_version`, a view reads every file stored now, including any a stopped run left.
- **The API** pins each request to the store's newest version, `latest_data_version(store)`, and echoes it as `data_version`. It's `null` only if the store has no version yet: run any ingestion command once, even one that answers from the cache.
- **Never delete or rewrite a file a version lists.** `write_rows` never does. Rebuilding a table by deleting its folder breaks the versions that list its files (see [Store](#point-in-time-data-layer)).

## Ingestion

From `backend/`, run each source once, one after another:

```bash
uv run python -m app.data.ingest fred     # macro vintages (ALFRED)
uv run python -m app.data.ingest sec      # company identity, then filing histories (EDGAR)
uv run python -m app.data.ingest tiingo   # raw daily prices and corporate actions
```

From another folder, use `uv run --directory <path to backend> python -m app.data.ingest <source>`. Add `--refresh` to download again instead of answering from the raw cache.

Each command loads its whole catalog: there's no option for a single series or ticker. Run them one at a time, never in parallel, because the store expects one writer per table. First runs took the times below: `fred` on 2026-10-23, and `sec` and `tiingo` for universe v1 (S6.5) on 2026-10-31:

| Source | Requests | Time | What it loads |
| --- | ---: | ---: | --- |
| `fred` | 18 | 6 s | Every vintage of the series in [`sources/alfred_series.toml`](app/data/sources/alfred_series.toml), UNRATE first, into `macro_observations` (S4.2). Each request asks for ALFRED's whole real-time range, because FRED's defaults return today's revised values. |
| `sec` | 312 | 54 s | First, identity and membership: the curated ticker history in [`sources/securities.toml`](app/data/sources/securities.toml) into `securities`, a snapshot of SEC's ticker file into `sec_tickers` (S5.2), and the universes in [`sources/universes.toml`](app/data/sources/universes.toml) into `universe_members` (S6.5). It warns when a curated security's current ticker isn't in SEC's file. Then the filing histories of every universe member and SPY, AAPL first, older pages included, into `filings` (S5.3). The big banks' histories run to dozens of pages each. Only 10-K, 10-Q, and 8-K filings and their amendments are kept. Each filing is known at its EDGAR acceptance time, corrected for the Eastern-offset shift where the company's file has one (see [`doc/data-sources.md`](../doc/data-sources.md#sec-edgar-filing-history-submissions-api)), and each amendment is linked to the filing it amends. Right after each company's filings come its XBRL company facts, if it files any, for the curated concepts in [`sources/xbrl.py`](app/data/sources/xbrl.py), into `xbrl_facts` (S5.5). Each fact is known at the acceptance time of the filing that reported it, or at the end of its filed date, flagged, when that filing isn't in `filings`. |
| `tiingo` | 51 | 26 s, then a rerun an hour later | The curated `securities` and membership, then raw daily bars for every universe member and SPY into `price_bars`, and the splits and dividends they report into `corporate_actions` (S6.2). A first run loads each security from 2005. Loading universe v1 from scratch takes one request more than Tiingo's 50 an hour, so the first run stops at the limit and a rerun an hour later finishes; only the run that finishes writes a data version. Later runs ask only for sessions after its last stored bar, through the last one Tiingo has settled (20:00 ET), and log any session that comes back without a bar. Adjusted prices are never stored. |

Each ingester lives in [`app/data/sources/`](app/data/sources/) and is listed in `INGESTERS` in [`app/data/ingest.py`](app/data/ingest.py).

**Coverage of the standard metrics.** After `ingest sec`, run `uv run python -m app.data.coverage`. It reads the store as the API does, pinned to the newest data version, and prints Markdown. For each metric in [`sources/metrics.toml`](app/data/sources/metrics.toml), and each company that was ever in the universe, it shows how many of the company's 10-Qs and 10-Ks reported one of the metric's concepts for their own period, which concepts they used, and which periods none covered.

- **Options:** `--as-of` for an earlier knowledge time, and `--metric` (repeatable) for fewer metrics.
- **What to look for:** a company that misses periods, or whose concept switches to one with different values for the same period. Either may need an override in `metrics.toml`, with its reason and source.
- **After adding a concept,** run `ingest sec` again. It answers from the raw cache.

**Data versions.** When a command finishes, it writes a [data version](#data-versions), and its log ends with `Data version 20261101T143005Z: … rows in … files`, or with "unchanged" when the run added nothing. A run that fails or stops at a rate limit writes none, so the API keeps serving the version before it.

**Release times.** Each vintage counts as known on its date at its release's time, New York time: 08:30 for BLS's and BEA's releases, 16:15 for the Fed's H.15 (S4.3). The times and their sources are in `alfred_series.toml`, and [`doc/time-model.md`](../doc/time-model.md) (rule 7) summarizes them. A release whose time isn't known (`time = "unknown"`) makes its vintages known at the end of their date, flagged `time_assumed`.

To add a macro series, add it to `alfred_series.toml` with FRED's metadata and its release, then run `ingest fred` again. A new release needs its time and a source for it.

**Picking up new data.**

- **`tiingo`** asks for new sessions on every run.
- **`fred` and `sec`** request the same URLs every time, so a plain re-run answers from the raw cache and adds nothing. Run them with `--refresh` to fetch new vintages, filings, and company facts.
- **`sec --refresh`** also stores a new snapshot of SEC's ticker file.

**Exit codes.**

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | A rate limit, a failed download, or data the ingester refused. The message says why, and for a rate limit, when to run again. |
| 2 | A missing setting, such as `SEC_USER_AGENT`, or an unknown source |

**Raw cache.** Every response is saved as it arrived, with a metadata file: the URL without secrets, the status, and the fetch time. A re-run answers from the cache, and `--refresh` downloads again. API keys are never written to disk or to the command's log. Every source answers in JSON, so a page that isn't JSON (FRED serves an HTML page with status 200 while it's down for maintenance) counts as a failed request and isn't cached.

**Rate limits.** The client stays within each source's limits and retries failures with backoff:

| Source | Limit |
| --- | --- |
| SEC EDGAR | 10 requests per second, with `SEC_USER_AGENT` |
| FRED | 120 requests per minute |
| Tiingo | 50 per hour and 1,000 per day (free plan; also 500 symbols per month) |

When a limit would mean waiting more than a minute, the command stops and says when to run it again. The re-run reuses the cache, so it picks up where it stopped.

## Data layout

Everything lives under `DATA_DIR` (`backend/data/` by default), which git ignores. Nothing in it may be committed: Tiingo's terms forbid sharing its data.

```
data/
├── raw/<source>/<ab>/<sha256>.body   # each response exactly as received (fred, sec, tiingo)
│                    <sha256>.json    # its metadata: the URL without keys, status, fetch time
├── store/<table>/part-<ingested_at>-<id>.parquet   # zstd, sorted by key, then available_at
│        _versions/<data_version>.json             # one manifest per data version (S3.7)
└── samples/<name>.csv                # output of the sample-data scripts (testing only)
```

- **Raw cache.** `<sha256>` hashes the method and the URL, with its query sorted and its keys removed; `<ab>` is the hash's first two characters.
- **Store.** Every write that adds rows creates a new Parquet file, so files accumulate. For example, `fred` writes one per series on each run that finds new vintages. Every file carries the provenance columns.
- **Data versions.** `store/_versions/` holds one manifest per finished ingestion run, which names its files relative to `store/`. Keep it with the store: copying or uploading `store/` takes it along.

| Table | Key | Holds |
| --- | --- | --- |
| `macro_observations` | `series_id`, `observation_date` | Every published version of each observation, from ALFRED |
| `securities` | `security_id` | Each curated security's ticker, name, and CIK over time |
| `sec_tickers` | `cik`, `ticker` | Snapshots of SEC's ticker file |
| `price_bars` | `security_id`, `session_date` | Raw daily bars, as traded |
| `corporate_actions` | `security_id`, `ex_date`, `action` | Splits and cash dividends by ex-date |
| `filings` | `cik`, `accession_number` | 10-K, 10-Q, and 8-K filings and their amendments, from EDGAR |
| `xbrl_facts` | `cik`, `accession_number`, `concept`, `unit`, `period_end`, `duration_days`, `value` | Each XBRL fact in the curated concepts as each filing reported it; a value repeated in a later filing is another row, known from that filing's acceptance time |
| `universe_members` | `universe`, `security_id`, `added` | Each curated universe's membership spells; a removal is a second version, known from its own date |

After loading universe v1 on 2026-10-31, the store held 305,139 rows in 163 files, 7.5 MB in all, and the raw cache 159 MB, mostly EDGAR's submission files. The M2 set alone had been 65,829 rows in 1.2 MB. Only the store is needed to serve the API. `uv run python -m spikes.hosting` reports both by table and source.

## Deployment

The API was deployed to Fly.io at <https://quant-time-machine-api.fly.dev>, as a container built from [`Dockerfile`](Dockerfile) and configured by [`fly.toml`](fly.toml), with the store on a volume (D4). It ran on Fly's free trial, which lapsed on 2026-10-31, so that URL no longer answers. The team deferred adding a card until a host is needed, before S8.4, so develop against a local backend until then. AWS Lambda is the lead candidate for that host, and a spike before S8.4 decides between it and Fly. [`doc/hosting.md`](../doc/hosting.md) has the decision, the steps to deploy and to upload the store, and what's still to do for S15.1. The deployment never sets `SERVE_RAW_PRICES`, so its `/v1/prices` answers 403.

`.dockerignore` keeps `data/` and `.env` out of the build, because flyctl sends whatever isn't excluded there, git-ignored or not. Keep it that way.

**Pending: upload the universe v1 store.** Skipped in Sprint 3 until D4 picks the host (AWS Lambda, or Railway once it reopens). The store to deploy is the one ingested for universe v1 (S6.5): all of `DATA_DIR/store`, `_versions/` included, so the host serves the same data versions as the machine that ingested. [`doc/hosting.md`](../doc/hosting.md#next-steps-for-s151) tracks it.

## Spikes

[`spikes/`](spikes/) holds the experiments behind the data, storage, and hosting decisions: the ALFRED, EDGAR, and price-source explorations, the storage benchmark, and the hosting measurements. See [`spikes/README.md`](spikes/README.md) for what each needs and how to run it. Their findings are written up in [`doc/data-sources.md`](../doc/data-sources.md), [`doc/storage.md`](../doc/storage.md), and [`doc/hosting.md`](../doc/hosting.md).

## Sample-data scripts

Four scripts in [`app/data/`](app/data/) pull a small sample (five tickers, 2010–2015) for testing, apart from ingestion. They aren't the supported pipeline. Their CSVs carry a date-only `available_date`, and their `get_*_as_of` helpers are coarse date filters that don't enforce the publication times in [`doc/time-model.md`](../doc/time-model.md); real reads go through `PointInTimeView`. The packages they need aren't backend dependencies, so `uv run --with` adds them for one run. From `backend/`:

| Script | Pulls | Needs | Command |
| --- | --- | --- | --- |
| [`fetch_market_prices.py`](app/data/fetch_market_prices.py) | Daily bars from Yahoo via yfinance, adjusted for later splits and dividends | Nothing | `uv run --with yfinance python -m app.data.fetch_market_prices` |
| [`fetch_economic_data.py`](app/data/fetch_economic_data.py) | ALFRED vintages of UNRATE, CPIAUCSL, and GDP | `FRED_API_KEY` | `uv run --with requests python -m app.data.fetch_economic_data` |
| [`fetch_sec_filings.py`](app/data/fetch_sec_filings.py) | Revenue and net income from EDGAR's XBRL company facts | `SEC_USER_AGENT` | `uv run --with requests python -m app.data.fetch_sec_filings` |
| [`upload_to_supabase.py`](app/data/upload_to_supabase.py) | Copies the three CSVs into Supabase tables of the same names | `SUPABASE_URL`, `SUPABASE_KEY` | `uv run --with supabase python -m app.data.upload_to_supabase` |

The CSVs go to `DATA_DIR/samples/`, which git ignores; never commit them. Each script's docstring lists its fields and limitations. The yfinance prices are not as traded: AAPL's close on 2012-09-19 comes out as 21.09, against $702.10 as traded.

## Design principles (draft)

- **No look-ahead.** Every data record carries the time it became publicly available, and all reads go through "as of" queries, so a simulation can only see what was known on its simulated date. The rules are in [`doc/time-model.md`](../doc/time-model.md).
- **Deterministic calculations.** The same inputs always produce the same results. Any future AI assistant helps plan experiments, while plain, tested code does the calculations.
