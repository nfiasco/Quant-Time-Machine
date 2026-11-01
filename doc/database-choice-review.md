# Database choice review: Quant Time Machine

**Reviewed October 20, 2026. Recommendation; does not replace decision D1.**

**Recommendation: keep DuckDB for analytics and Supabase/PostgreSQL for application state.** DuckDB fits the current scope: roughly 100 securities, daily data, SEC fundamentals, macro vintages, and monthly backtests. Local Python execution and limited operating effort suit the capstone. [Project requirements](roadmap.md), [DuckDB design](https://duckdb.org/why_duckdb).

**ClickHouse is the strongest analytical challenger. DuckLake is the most relevant storage improvement.** Evaluate them before treating the choice as final. Changing remains feasible; existing implementation work is not the reason to retain DuckDB.

**What the evidence says.** The repository's synthetic benchmark measured the 180-date analytical query at **21.6 ms with DuckDB over Parquet**, versus **347.9 ms with PostgreSQL**. PostgreSQL was faster for individual lookups. These warm, local measurements exclude the complete backtest, realistic concurrency, and API overhead. They support DuckDB's fit but do not establish a universal winner. No comparative benchmark of the additional candidates was performed. [Benchmark and limitations](storage.md), [benchmark script](../backend/spikes/storage_benchmark.py).

**The alternatives that matter most**

| Option | Main advantage | Assessment for this project |
| --- | --- | --- |
| **DuckLake** | Catalog, snapshots, and transactions around analytical files | Evaluate before building custom dataset manifests. It complements DuckDB rather than replacing the engine. [Docs](https://ducklake.select/docs/stable/duckdb/advanced_features/transactions) |
| **ClickHouse** | Shared analytical service with native as-of joins | Benchmark against DuckDB, especially for concurrent backtests. Retain revision history explicitly. [Docs](https://clickhouse.com/docs/reference/statements/select/join) |
| **PostgreSQL / TimescaleDB** | Relational transactions and potential database consolidation | Plain PostgreSQL is viable. TimescaleDB adds time-series features, but Supabase deprecates it on Postgres 17, which this project targets. [Hosting caveat](https://supabase.com/docs/guides/database/extensions/timescaledb) |
| **XTDB** | Native valid-time and system-time history | Strong if temporal corrections become the dominant engineering problem. Public availability still needs deliberate modeling. [Docs](https://docs.xtdb.com/about/time-in-xtdb.html) |
| **ArcticDB / Dolt** | Versioned DataFrames / database commits and branches | Consider if reproducible Python datasets or reviewing data changes becomes central. Both change the integration model. [ArcticDB](https://docs.arcticdb.io/latest/tutorials/snapshots/), [Dolt](https://www.dolthub.com/docs/sql-reference/version-control/querying-history/) |
| **MotherDuck** | Managed DuckDB-based analytics | Useful when managed hosting saves enough effort to justify service costs and limits. [Architecture](https://motherduck.com/learn/how-motherduck-scales-distributed-architecture/) |
| **InfluxDB 3** | Time-series ingestion and SQL analytics | Weaker fit for multiyear research. Core defaults to a configurable 432-file query limit, often described as roughly 72 hours; this is not an age limit on stored data. Enterprise supports broader historical queries. [Core limits](https://docs.influxdata.com/influxdb3/core/reference/config-options/), [Enterprise](https://docs.influxdata.com/influxdb3/enterprise/) |

Other researched options have less compelling reasons to adopt them now:

- **Snowflake / BigQuery:** reconsider if institutional access, credits, or existing datasets favor a managed warehouse.
- **QuestDB / kdb+ / KDB-X:** stronger candidates if tick or intraday data enters scope.
- **Doris / StarRocks / Druid / Pinot:** credible analytical services; lower evaluation priority than ClickHouse for this workload.
- **CockroachDB:** reconsider for demanding distributed application transactions.
- **Iceberg / Delta Lake:** alternative table formats if lakehouse interoperability becomes important; they still need a query engine.

These are workload-fit judgments, not measured performance rankings.

**The main unresolved issue is reproducibility.** Every option must distinguish the observation date, when information became public, and which dataset version a saved run used. A filing from 2020 loaded in 2026 can belong in a 2020 simulation; a later public restatement cannot appear before its publication date.

The current [`PointInTimeView`](../backend/app/data/view.py) does not implement persistent `data_version` selection (S3.7 has since added it; see the outcome below). The [`writer`](../backend/app/data/store.py) also needs coordinated ingestion, complete-batch publication, and corrections that preserve old inputs. Database “time travel” alone does not supply these guarantees.

Two storage pitfalls matter:

- ClickHouse's `ReplacingMergeTree` can discard earlier revisions when keys match. Preserve immutable history rather than relying only on the latest value. [Semantics](https://clickhouse.com/docs/reference/engines/table-engines/mergetree-family/replacingmergetree)
- DuckLake still needs application deduplication and a retention policy protecting snapshots referenced by saved runs. [Constraints](https://ducklake.select/docs/stable/duckdb/unsupported_features), [retention](https://ducklake.select/docs/stable/duckdb/maintenance/expire_snapshots)

**Next steps**

1. Compare DuckDB with ClickHouse using representative data and complete backtests; include PostgreSQL if consolidation is a priority.
2. Evaluate DuckLake against a small immutable-manifest design. Verify old-run replay after corrections, failed ingestion, cleanup, and restart.
3. Measure the intended deployment against the **300 ms lookup** and **60-second backtest** targets, including concurrency, memory, and operating cost.

Switch when another design demonstrably improves correctness, meets an unmet requirement, or reduces total effort. The current evidence favors keeping DuckDB while completing dataset versioning.

**Outcome for Sprint 3 (2026-10-29, pending team review).** D1 stays: Parquet files queried with DuckDB. Data versions (S3.7) use the small immutable manifest the roadmap already specifies, not DuckLake. The manifest design takes on the requirements above:

- **One manifest per completed ingestion run.** It lists the sources, row counts, each Parquet file with its content hash, and the latest `ingested_at`. The `data_version` names that manifest.
- **Written last.** A run that fails part way writes no manifest, so no data version points to a partial batch.
- **A pinned view reads only its manifest's files**, filtered to `ingested_at` at or before the manifest's. If a listed file is missing or its hash differs, the view raises an error instead of answering from different data.
- **Files a manifest lists are never deleted or rewritten.** A correction or rebuild writes new files and a new manifest, so old runs replay unchanged. Compacting files would follow the same rule.

DuckLake and ClickHouse remain later comparisons (steps 1 and 2 above). Revisit them if the manifest can't meet these rules, if ingestion needs more than one writer, or if a backtest misses the 60-second target because of storage.

**Implemented in S3.7 (2026-10-31).** [`app/data/versions.py`](../backend/app/data/versions.py) writes the manifest at the end of each `ingest` run, and `PointInTimeView` pins to it, as described above. Three choices were made along the way:

- **Names.** A data version is named by when it was cut, such as `20261101T143005Z`.
- **Checks.** A pinned view checks every listed file's size each time it opens, and its SHA-256 the first time in a process. Hashing on every open would slow every request as the store grows.
- **Rebuilds.** Deleting a table to rebuild it still breaks the versions that list its files, but they now fail clearly. Retiring old files instead of deleting them can wait until saved runs exist (S7.7).
