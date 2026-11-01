# Point-in-time storage (decision D1)

> **Spike S3.2.** Decided 2026-10-11, pending team review. Evidence: [`backend/spikes/storage_benchmark.py`](../backend/spikes/storage_benchmark.py), which anyone can re-run in about 15 seconds.

## Decision

**Store point-in-time data as Parquet files under `DATA_DIR`, and query them with DuckDB running inside the backend process.** There is no database server to run.

User accounts and each user's own data (sign-in, saved experiments and runs) are a separate job with different needs. They go in Supabase (PostgreSQL plus Supabase Auth), which a teammate set up in [`supabase/`](../supabase/) for that purpose. See [two stores](#two-stores-point-in-time-data-and-accounts) below.

Why:

1. **It's fastest on the queries the product runs most.** On 1M rows, a full "as of *T*" snapshot took about 4 ms in DuckDB, 40 ms in PostgreSQL, and 280 ms in SQLite. A backtest-style as-of join over 180 decision dates took about 20 ms, 350 ms, and 270 ms.
2. **Single lookups are fast everywhere** (under 2 ms), so the 300 ms API target (NFR-5) doesn't separate the engines. The analytical queries do.
3. **DuckDB's `ASOF JOIN` says "latest row with `available_at ≤ T`" directly**, which is exactly our core question.
4. **No server.** The same code runs in the API, in tests, and in notebooks. Test fixtures are just small files, so CI needs no database service.
5. **Parquet files are immutable**, which fits an append-only store. A data version (S3.7) can be a manifest of files and their hashes.
6. **It's small.** The 1M-row dataset took 2.2 MB as Parquet and 18 MB as a DuckDB file, against 150 MB in PostgreSQL with indexes. That matters on free hosting tiers.

## The benchmark

Run it from `backend/` with `uv run --python 3.12 spikes/storage_benchmark.py`. Add `--postgres-dsn` to point it at another PostgreSQL server, such as a local Supabase database.

**Data.** 1,000,000 deterministic synthetic rows: 1,000 entities × 250 periods × 4 versions. Each row has `entity_id`, `period`, `version`, an integer `value`, `available_at`, and `ingested_at` (timestamps in UTC). The first version of a period is published 20 to 29 days after it; each revision comes 90 days later. `available_at` is unique within an entity, so ASOF joins have no ties.

**Engines.**

| Engine | Setup |
| --- | --- |
| DuckDB table | DuckDB 1.5.6, a file-backed database |
| Parquet + DuckDB | One zstd-compressed Parquet file, sorted by key and time, read by a fresh in-memory DuckDB |
| PostgreSQL | 16.2, an embedded throwaway server via pgserver, default settings, `COPY` load, then B-tree indexes on `(entity_id, period, available_at DESC) INCLUDE (value)` and `(entity_id, available_at DESC) INCLUDE (value)`, then `VACUUM ANALYZE` |
| SQLite | 3.45.3, timestamps stored as integer microseconds, matching indexes, then `ANALYZE` |

**Queries.**

| Query | Question | DuckDB | PostgreSQL | SQLite |
| --- | --- | --- | --- | --- |
| Q1 snapshot | Latest version of every (entity, period) with `available_at ≤ T` | `QUALIFY row_number() …` (and an `ASOF JOIN` variant) | `DISTINCT ON` | `row_number()` subquery |
| Q2 lookup | Q1 for one entity: a proxy for one API call | Q1 with `entity_id = ?` | Q1 with `entity_id = …` | Q1 with `entity_id = …` |
| Q3 backtest | For each of 180 monthly decision times and each entity, the most recent row published by then | `ASOF LEFT JOIN` | `LEFT JOIN LATERAL (… ORDER BY available_at DESC LIMIT 1)` | Correlated subquery |

Q1 and Q3 ask different questions. Q1 is "the latest version of each period", what a fundamentals or macro snapshot needs. Q3 is "the latest thing published", what a signal evaluated at each rebalance needs.

**Results** (retrieved 2026-10-11 on an Apple M3 Pro with 11 cores and 18 GB RAM, macOS 27). Each cell is the first run / the median of 5 warm runs, in milliseconds:

| Engine | Q1 snapshot | Q1 via ASOF | Q2 lookup | Q3 backtest |
| --- | --- | --- | --- | --- |
| DuckDB table | 4.1 / 3.8 | 18.8 / 19.8 | 1.8 / 0.5 | 18.2 / 19.5 |
| Parquet + DuckDB | 5.9 / 5.9 | 19.9 / 21.9 | 3.1 / 1.7 | 20.7 / 21.6 |
| PostgreSQL 16 | 47.1 / 40.4 | n/a | 0.3 / 0.1 | 362.0 / 347.9 |
| SQLite | 290.9 / 276.5 | n/a | 0.4 / 0.3 | 264.6 / 270.4 |

| Engine | Load and index time | Size on disk |
| --- | --- | --- |
| DuckDB table | 0.24 s (includes generating the data) | 18.4 MB |
| Parquet | 0.02 s (written from the DuckDB table) | 2.2 MB |
| PostgreSQL 16 | 1.46 s | 149.9 MB (table and indexes) |
| SQLite | 1.30 s | 79.8 MB |

All four engines returned identical answers: Q1 gives 151,000 rows, Q2 gives 151, and Q3 gives 180,000. The script checks this with exact integer checksums.

**Caveats.**

- **One laptop, warm caches, local disk.** A hosted PostgreSQL (Supabase, for example) would add network latency to every query.
- **Engines use the hardware differently.** DuckDB uses every core; SQLite uses one.
- **PostgreSQL ran with default settings.** Tuning (`work_mem`, parallel workers) would narrow the Q1 gap, but not the Q3 gap: Q3 is 180,000 separate index lookups.
- **Synthetic data compresses better than real data**, so read the sizes as relative.
- **Load times aren't comparable across engines.**
- **The ASOF form of Q1 was slower than `QUALIFY`.** Building the grid of keys first costs time. For a single snapshot, `QUALIFY` (or `arg_max`) is the better form; `ASOF JOIN` earns its keep when there are many decision times.

## How to write an as-of query (example for the team)

```sql
-- What did we know about every series and observation date at 09:30 ET on June 5, 2020?
SELECT series_id, observation_date, value, available_at
FROM read_parquet('data/store/macro_observations/*.parquet')
WHERE available_at <= TIMESTAMPTZ '2020-06-05 13:30:00+00'
QUALIFY row_number() OVER (
    PARTITION BY series_id, observation_date ORDER BY available_at DESC
) = 1;

-- For each rebalance date and security, the latest price bar that had closed by the decision time.
SELECT g.decision_time, g.security_id, b.session_date, b.close
FROM (SELECT d.decision_time, u.security_id FROM decisions d CROSS JOIN universe u) g
ASOF JOIN price_bars b
  ON b.security_id = g.security_id
 AND b.available_at <= g.decision_time;
```

In Python, `duckdb.connect()` gives an in-process database; `con.execute(sql, params).fetchall()` (or `.df()`) runs a query. S3.3 wraps this in `PointInTimeView`, so application code never writes the `available_at` filter by hand.

## Fit with hosting (input to S1.6 and D4)

**Data size.** The starter universe should be roughly a million rows, the same order of magnitude as this benchmark:

- daily bars for about 100 securities from 2005 to 2025 (about 5,300 sessions each)
- filings and XBRL facts for the same companies
- full vintage histories of six macro series

As Parquet, that is tens of megabytes.

| Option | DuckDB + Parquet | PostgreSQL |
| --- | --- | --- |
| Vercel Functions (serverless) | Works. Python bundles can be up to 500 MB uncompressed, so the Parquet files can ship with the code, or DuckDB can read them from object storage. The filesystem isn't persistent, so ingestion runs elsewhere. Limits: 300 s per request on Hobby, 2 GB memory, 4.5 MB response bodies. | Needs a separate hosted database, with a network hop on every query. |
| Container host (Render, Railway, Fly.io) | Works best with a persistent disk. Render's free tier has no persistent disk and sleeps after 15 minutes idle (about a minute to wake), so data would have to be baked into the image or fetched at startup. | Same, plus a database service. |
| Object storage (S3, R2) | Parquet files can live there and be read remotely with DuckDB's `httpfs` extension. Simple and cheap; latency is higher than local files. | Not applicable. |
| Supabase (managed PostgreSQL) | Not needed for this data. Supabase holds accounts and user data instead. | Free plan: 500 MB database, 2 active projects, paused after a week without activity. 150 MB per million rows with indexes leaves little headroom. Pro is $25/month. |

Sources: [Vercel Functions limits](https://vercel.com/docs/functions/limitations), [Render free instances](https://render.com/docs/free), [Supabase pricing](https://supabase.com/pricing), all retrieved 2026-10-11.

S1.6 made the hosting decision (D4) in [`hosting.md`](hosting.md), with the store's real size measured: 65,829 rows in 1.2 MB of Parquet for the M2 set, about 17.5 bytes per row.

## Two stores: point-in-time data and accounts

The system keeps two kinds of data with opposite needs, so they live in different places. Only one of them is a database server.

| | Point-in-time store | Accounts and user data |
| --- | --- | --- |
| What | Prices, filings, XBRL facts, macro vintages, data-version manifests | Users and sign-in, saved experiment specs, run records and results, settings; chat history in CISC 499 |
| Shared by | Everyone: the facts are the same for every user | One user each |
| Written by | Ingestion jobs only, append-only | Users, through the app, at any time |
| Read as | Large scans and as-of joins | Small lookups by user |
| Lives in | Parquet files under `DATA_DIR`, queried by DuckDB inside the backend | Supabase: hosted PostgreSQL plus Supabase Auth |
| Why there | 10 to 18× faster for our queries, no server to run, and immutable files for data versions | Built-in sign-in and sessions, safe concurrent writes, and row-level security |

How a signed-in request flows:

1. The browser signs in with Supabase Auth and receives an access token (a JWT).
2. It calls our FastAPI backend with that token, and the backend verifies it to learn the user's ID.
3. The backend reads market data through `PointInTimeView` (DuckDB), which knows nothing about users, and runs the backtest.
4. It saves the run in Supabase under that user's ID: the spec, the data version it used, and the results.

Rules that keep the two apart:

- **Never copy point-in-time data into Supabase.** A user's run points to the data through its `data_version` (S3.7). This also keeps raw vendor prices out of user storage.
- **Turn on row-level security for every user table**, so people can read and write only their own rows.
- **Keep the secret key on the server.** The project's public key (Supabase calls it the anon or publishable key) can go in the browser as a `NEXT_PUBLIC_` variable. The secret (service-role) key stays on the server only (NFR-8).
- **Publish a privacy policy.** Accounts mean we collect personal data, at least an email address. FRED's terms also require a privacy policy for apps that collect user information.
- **Signing in doesn't change data licenses.** Signed-in users are still "other people" under Tiingo's internal-use terms (D2).
- **Keep the project awake before demos.** Supabase's free plan pauses a project after a week without activity, so use it before demos (or upgrade for the demo month).

The `supabase/` folder holds only the generated `config.toml` (PostgreSQL 17, plus Auth, Storage, and Studio), with no schema yet. Running Supabase locally needs Docker and the Supabase CLI; the hosted project needs neither. To benchmark its database against the numbers above, start it with `supabase start` and run:

```bash
uv run --python 3.12 spikes/storage_benchmark.py --postgres-dsn postgresql://postgres:postgres@127.0.0.1:54322/postgres
```

## What this means for M2

- **Layout.** Raw responses go under `DATA_DIR/raw/<source>/` (S3.4). Normalized, append-only tables go under `DATA_DIR/store/<table>/` as Parquet. As of Sprint 2 they are:
  - `macro_observations`
  - `securities` and `sec_tickers`
  - `price_bars` and `corporate_actions`
  - `filings`

  XBRL facts get their table in S5.5. `DATA_DIR` is git-ignored, and [`backend/README.md`](../backend/README.md#data-layout) shows the layout file by file.
- **Columns.** Every table carries `available_at` and `ingested_at` (`TIMESTAMPTZ`, UTC), plus `source`, `source_ref`, and `time_assumed`, which flags an `available_at` that was assumed rather than published (time model, rule 11). Write files sorted by key and `available_at`, so DuckDB can skip what a query doesn't need.
- **Reads.** `PointInTimeView` (S3.3) opens one DuckDB connection with views over the Parquet files. Every read filters `available_at <= knowledge_time`. A view pinned to a data version (S3.7) also reads only the files that version's manifest lists, and only rows with `ingested_at` up to the manifest's latest. The API pins every request to the newest version.
  - **Dependencies.** The backend depends on `duckdb` and `pytz`; DuckDB's Python API needs `pytz` to return `TIMESTAMPTZ` values as `datetime` objects.
  - **Time zone.** Set `TimeZone = 'UTC'` on every connection, as `store.connect()` does. Otherwise DuckDB returns `TIMESTAMPTZ` values in the machine's local zone, so a Mac in New York and Linux CI would disagree.
  - **Naive timestamps.** DuckDB reads a naive timestamp cast to `TIMESTAMPTZ` as UTC without complaint, so the writer rejects naive datetimes before they reach DuckDB.
- **Ties.** Make `(key, available_at)` unique, or add a tie-breaker. `ASOF JOIN` picks an arbitrary row when two candidates have the same time.
- **Compaction.** Incremental ingestion creates many small files, so compact them now and then. Because readers use immutable Parquet files rather than a shared database file, ingestion and the API never contend for a single writer lock. A compaction must write new files and a new data version, and keep every file an older version lists (S3.7).
