# /// script
# requires-python = "==3.12.*"
# dependencies = ["duckdb==1.5.6", "psycopg[binary]==3.3.6", "pgserver==0.1.4"]
#
# [tool.uv]
# exclude-newer = "2026-10-12T00:00:00Z"
# ///
"""Spike S3.2: which storage engine makes point-in-time ("as of") queries simple and fast?

Run from backend/:  uv run --python 3.12 spikes/storage_benchmark.py
(--python 3.12 is needed because backend/.python-version says 3.14, and pgserver, which
provides a throwaway PostgreSQL server with nothing to install, only ships wheels up to 3.12.)
Use --postgres-dsn to test another PostgreSQL server instead, for example a local Supabase
database: postgresql://postgres:postgres@127.0.0.1:54322/postgres. The benchmark works in its
own schema there and drops it afterwards.

It builds about 1M deterministic synthetic rows, one per (entity, period, version), each with an
available_at time, and loads them into DuckDB, Parquet (queried with DuckDB), PostgreSQL, and
SQLite. Then it times three queries and checks that every engine returns identical results:

  Q1  Snapshot: the latest version of every (entity, period) with available_at <= T.
  Q2  Lookup: Q1 for one entity, a proxy for a single API call (NFR-5 targets under 300 ms).
  Q3  Backtest: for each of 180 monthly decision times and each entity, the most recent row
      published by then (DuckDB ASOF JOIN, PostgreSQL LATERAL, SQLite correlated subquery).

Everything is written to a temporary directory that is deleted at the end.
"""

import argparse
import os
import platform
import shutil
import sqlite3
import statistics
import subprocess
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import psycopg

T = datetime(2012, 6, 5, 13, 30, tzinfo=UTC)  # 09:30 ET on June 5, 2012
LOOKUP_ENTITY = 42
EPOCH_2000_US = 946_684_800_000_000
DAY_US = 86_400_000_000

# Deterministic data: no randomness, so every engine and every run sees the same rows.
# Version 1 of a period is published 20-29 days after the period, and each revision 90 days later.
# Values are integers, so sums compare exactly. The microsecond term makes available_at unique
# within an entity, which ASOF JOIN needs to avoid ties.
GENERATE = """
CREATE TABLE facts AS
SELECT
    entity_id::INTEGER AS entity_id,
    period::INTEGER AS period,
    version::INTEGER AS version,
    entity_id * 1000000 + period * 10 + version AS value,
    make_timestamp(
        {epoch} + (period * 30 + 20 + entity_id % 10 + (version - 1) * 90) * {day}
        + 45000000000 + period * {versions} + version
    )::TIMESTAMPTZ AS available_at,
    available_at + INTERVAL 1 HOUR AS ingested_at
FROM range(1, {entities} + 1) AS e(entity_id),
     range({periods}) AS p(period),
     range(1, {versions} + 1) AS v(version)
ORDER BY entity_id, period, available_at
"""

DUCKDB = {
    "Q1": """
        SELECT count(*), sum(value) FROM (
            SELECT value FROM facts WHERE available_at <= ?::TIMESTAMPTZ
            QUALIFY row_number() OVER (PARTITION BY entity_id, period ORDER BY available_at DESC) = 1
        )""",
    "Q1 (ASOF)": """
        SELECT count(*), sum(f.value)
        FROM (SELECT e.entity_id, p.period, ?::TIMESTAMPTZ AS t
              FROM entities e CROSS JOIN periods p) k
        ASOF JOIN facts f
          ON f.entity_id = k.entity_id AND f.period = k.period AND f.available_at <= k.t""",
    "Q2": """
        SELECT count(*), sum(value) FROM (
            SELECT value FROM facts WHERE entity_id = ? AND available_at <= ?::TIMESTAMPTZ
            QUALIFY row_number() OVER (PARTITION BY period ORDER BY available_at DESC) = 1
        )""",
    "Q3": """
        SELECT count(*), count(f.value), sum(f.value)
        FROM (SELECT e.entity_id, d.t FROM entities e CROSS JOIN decisions d) g
        ASOF LEFT JOIN facts f ON f.entity_id = g.entity_id AND f.available_at <= g.t""",
}

POSTGRES = {
    "Q1": """
        SELECT count(*), sum(value) FROM (
            SELECT DISTINCT ON (entity_id, period) value FROM facts
            WHERE available_at <= %(t)s
            ORDER BY entity_id, period, available_at DESC
        ) latest""",
    "Q2": """
        SELECT count(*), sum(value) FROM (
            SELECT DISTINCT ON (period) value FROM facts
            WHERE entity_id = %(entity)s AND available_at <= %(t)s
            ORDER BY period, available_at DESC
        ) latest""",
    "Q3": """
        SELECT count(*), count(f.value), sum(f.value)
        FROM decisions d CROSS JOIN entities e
        LEFT JOIN LATERAL (
            SELECT value FROM facts
            WHERE facts.entity_id = e.entity_id AND facts.available_at <= d.t
            ORDER BY facts.available_at DESC
            LIMIT 1
        ) f ON true""",
}

SQLITE = {
    "Q1": """
        SELECT count(*), sum(value) FROM (
            SELECT value, row_number() OVER (
                PARTITION BY entity_id, period ORDER BY available_at DESC) AS rn
            FROM facts WHERE available_at <= :t
        ) WHERE rn = 1""",
    "Q2": """
        SELECT count(*), sum(value) FROM (
            SELECT value, row_number() OVER (PARTITION BY period ORDER BY available_at DESC) AS rn
            FROM facts WHERE entity_id = :entity AND available_at <= :t
        ) WHERE rn = 1""",
    "Q3": """
        SELECT count(*), count(f.value), sum(f.value)
        FROM decisions d CROSS JOIN entities e
        LEFT JOIN facts f ON f.rowid = (
            SELECT rowid FROM facts
            WHERE facts.entity_id = e.entity_id AND facts.available_at <= d.t
            ORDER BY facts.available_at DESC
            LIMIT 1
        )""",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Point-in-time storage benchmark (spike S3.2)."
    )
    parser.add_argument("--entities", type=int, default=1000)
    parser.add_argument("--periods", type=int, default=250)
    parser.add_argument("--versions", type=int, default=4)
    parser.add_argument(
        "--runs", type=int, default=5, help="warm runs per query, after one first run"
    )
    parser.add_argument(
        "--postgres-dsn", help="use this PostgreSQL server instead of a throwaway one"
    )
    return parser.parse_args()


def decision_times() -> list[datetime]:
    """First day of each month, 2005-2019, at 13:30 UTC."""
    return [
        datetime(2005 + i // 12, 1 + i % 12, 1, 13, 30, tzinfo=UTC) for i in range(180)
    ]


def epoch_us(moment: datetime) -> int:
    return int(moment.timestamp()) * 1_000_000


def normalize(row: tuple) -> tuple:
    return tuple(None if value is None else int(value) for value in row)


def measure(run: Callable[[], tuple], runs: int) -> tuple[tuple, float, float]:
    """Return (result, first-run ms, median warm-run ms); every run must return the same result."""
    start = time.perf_counter()
    result = normalize(run())
    first = (time.perf_counter() - start) * 1000
    warm = []
    for _ in range(runs):
        start = time.perf_counter()
        assert normalize(run()) == result, "non-deterministic result"
        warm.append((time.perf_counter() - start) * 1000)
    return result, first, statistics.median(warm)


def sysctl(name: str) -> str:
    try:
        return subprocess.run(
            ["sysctl", "-n", name], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def megabytes(size: int) -> str:
    return f"{size / 1_000_000:.1f} MB"


def main() -> None:
    args = parse_args()
    times = decision_times()
    n_rows = args.entities * args.periods * args.versions
    work = Path(tempfile.mkdtemp(prefix="qtm-bench-"))
    results: dict[str, dict[str, tuple]] = {}
    timings: dict[str, dict[str, tuple[float, float]]] = {}
    loads: dict[str, tuple[float, str]] = {}
    versions: dict[str, str] = {
        "Python": platform.python_version(),
        "DuckDB": duckdb.__version__,
    }

    def add_key_tables(con: duckdb.DuckDBPyConnection) -> None:
        # Literal integers: DuckDB table functions don't take bound parameters everywhere.
        con.execute(
            f"CREATE TABLE entities AS SELECT range::INTEGER AS entity_id FROM range(1, {int(args.entities) + 1})"
        )
        con.execute(
            f"CREATE TABLE periods AS SELECT range::INTEGER AS period FROM range({int(args.periods)})"
        )
        con.execute("CREATE TABLE decisions (t TIMESTAMPTZ NOT NULL)")
        con.executemany("INSERT INTO decisions VALUES (?)", [(t,) for t in times])

    def record(engine: str, name: str, run: Callable[[], tuple]) -> None:
        result, first, warm = measure(run, args.runs)
        results.setdefault(engine, {})[name] = result
        timings.setdefault(engine, {})[name] = (first, warm)

    try:
        # --- DuckDB table (file-backed) ------------------------------------------------------
        duck = duckdb.connect(str(work / "bench.duckdb"))
        duck.execute("SET TimeZone = 'UTC'")
        start = time.perf_counter()
        duck.execute(
            GENERATE.format(
                epoch=EPOCH_2000_US,
                day=DAY_US,
                entities=args.entities,
                periods=args.periods,
                versions=args.versions,
            )
        )
        add_key_tables(duck)
        duck.execute("CHECKPOINT")
        loads["DuckDB table"] = (
            time.perf_counter() - start,
            megabytes((work / "bench.duckdb").stat().st_size),
        )
        rows = duck.execute("SELECT count(*) FROM facts").fetchone()[0]
        unique = duck.execute(
            "SELECT count(*) FROM (SELECT DISTINCT entity_id, available_at FROM facts)"
        ).fetchone()[0]
        assert rows == n_rows and unique == rows, (
            "available_at must be unique within each entity"
        )

        def duck_queries(engine: str, con: duckdb.DuckDBPyConnection) -> None:
            record(engine, "Q1", lambda: con.execute(DUCKDB["Q1"], [T]).fetchone())
            record(
                engine,
                "Q1 (ASOF)",
                lambda: con.execute(DUCKDB["Q1 (ASOF)"], [T]).fetchone(),
            )
            record(
                engine,
                "Q2",
                lambda: con.execute(DUCKDB["Q2"], [LOOKUP_ENTITY, T]).fetchone(),
            )
            record(engine, "Q3", lambda: con.execute(DUCKDB["Q3"]).fetchone())

        duck_queries("DuckDB table", duck)

        # --- Parquet file, queried by a fresh in-memory DuckDB ---------------------------------
        parquet = work / "facts.parquet"
        start = time.perf_counter()
        duck.execute(f"COPY facts TO '{parquet}' (FORMAT parquet, COMPRESSION zstd)")
        loads["Parquet + DuckDB"] = (
            time.perf_counter() - start,
            megabytes(parquet.stat().st_size),
        )
        lake = duckdb.connect()
        lake.execute("SET TimeZone = 'UTC'")
        lake.execute(f"CREATE VIEW facts AS SELECT * FROM read_parquet('{parquet}')")
        add_key_tables(lake)
        duck_queries("Parquet + DuckDB", lake)
        lake.close()

        # --- PostgreSQL ------------------------------------------------------------------------
        csv_path = work / "facts.csv"
        duck.execute(f"COPY facts TO '{csv_path}' (HEADER)")
        server = None
        dsn = args.postgres_dsn
        if dsn is None:
            import pgserver

            server = pgserver.get_server(work / "pgdata", cleanup_mode="delete")
            dsn = server.get_uri()
        try:
            with psycopg.connect(dsn, autocommit=True) as pg:
                pg.execute("SET TIME ZONE 'UTC'")
                exists = pg.execute(
                    "SELECT 1 FROM pg_namespace WHERE nspname = 'qtm_benchmark'"
                ).fetchone()
                if exists:
                    raise SystemExit(
                        "Schema qtm_benchmark already exists; drop it or use another database."
                    )
                pg.execute("CREATE SCHEMA qtm_benchmark")
                pg.execute("SET search_path = qtm_benchmark")
                versions["PostgreSQL"] = pg.execute("SHOW server_version").fetchone()[0]
                start = time.perf_counter()
                pg.execute(
                    """CREATE TABLE facts (
                        entity_id integer NOT NULL, period integer NOT NULL, version integer NOT NULL,
                        value bigint NOT NULL, available_at timestamptz NOT NULL,
                        ingested_at timestamptz NOT NULL)"""
                )
                with (
                    pg.cursor().copy(
                        "COPY facts FROM STDIN (FORMAT csv, HEADER true)"
                    ) as copy,
                    csv_path.open("rb") as source,
                ):
                    while chunk := source.read(1 << 20):
                        copy.write(chunk)
                pg.execute(
                    "CREATE INDEX facts_key_time ON facts (entity_id, period, available_at DESC) INCLUDE (value)"
                )
                pg.execute(
                    "CREATE INDEX facts_entity_time ON facts (entity_id, available_at DESC) INCLUDE (value)"
                )
                pg.execute(
                    f"CREATE TABLE entities AS SELECT generate_series(1, {int(args.entities)}) AS entity_id"
                )
                pg.execute("CREATE TABLE decisions (t timestamptz NOT NULL)")
                with pg.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO decisions VALUES (%s)", [(t,) for t in times]
                    )
                pg.execute("VACUUM ANALYZE facts")
                pg.execute("ANALYZE entities")
                pg.execute("ANALYZE decisions")
                size = pg.execute("SELECT pg_total_relation_size('facts')").fetchone()[
                    0
                ]
                loads["PostgreSQL"] = (
                    time.perf_counter() - start,
                    megabytes(size) + " (table + indexes)",
                )
                params = {"t": T, "entity": LOOKUP_ENTITY}
                for name, sql in POSTGRES.items():
                    record(
                        "PostgreSQL",
                        name,
                        lambda sql=sql: pg.execute(sql, params).fetchone(),
                    )
                pg.execute("DROP SCHEMA qtm_benchmark CASCADE")
        finally:
            if server is not None:
                server.cleanup()

        # --- SQLite (timestamps as integer microseconds since the epoch, UTC) ----------------
        lite = sqlite3.connect(work / "bench.sqlite")
        versions["SQLite"] = sqlite3.sqlite_version
        start = time.perf_counter()
        lite.execute("PRAGMA journal_mode = OFF")
        lite.execute("PRAGMA synchronous = OFF")
        lite.execute(
            """CREATE TABLE facts (
                entity_id INTEGER NOT NULL, period INTEGER NOT NULL, version INTEGER NOT NULL,
                value INTEGER NOT NULL, available_at INTEGER NOT NULL, ingested_at INTEGER NOT NULL)"""
        )
        source = duck.execute(
            "SELECT entity_id, period, version, value, epoch_us(available_at), epoch_us(ingested_at) FROM facts"
        )
        while batch := source.fetchmany(200_000):
            lite.executemany("INSERT INTO facts VALUES (?, ?, ?, ?, ?, ?)", batch)
        lite.execute(
            "CREATE INDEX facts_key_time ON facts (entity_id, period, available_at)"
        )
        lite.execute(
            "CREATE INDEX facts_entity_time ON facts (entity_id, available_at)"
        )
        lite.execute("CREATE TABLE entities (entity_id INTEGER PRIMARY KEY)")
        lite.executemany(
            "INSERT INTO entities VALUES (?)",
            [(e,) for e in range(1, args.entities + 1)],
        )
        lite.execute("CREATE TABLE decisions (t INTEGER NOT NULL)")
        lite.executemany(
            "INSERT INTO decisions VALUES (?)", [(epoch_us(t),) for t in times]
        )
        lite.commit()
        lite.execute("ANALYZE")
        loads["SQLite"] = (
            time.perf_counter() - start,
            megabytes((work / "bench.sqlite").stat().st_size),
        )
        params = {"t": epoch_us(T), "entity": LOOKUP_ENTITY}
        for name, sql in SQLITE.items():
            record("SQLite", name, lambda sql=sql: lite.execute(sql, params).fetchone())
        lite.close()
        duck.close()
    finally:
        shutil.rmtree(work, ignore_errors=True)

    # --- Report --------------------------------------------------------------------------------
    chip = sysctl("machdep.cpu.brand_string") or platform.processor()
    memory = sysctl("hw.memsize")
    print("# Storage benchmark (S3.2)\n")
    print(
        f"- Machine: {chip}, {os.cpu_count()} cores"
        + (f", {int(memory) / 2**30:.0f} GB RAM" if memory else "")
    )
    print(f"- OS: {platform.platform()}")
    print(
        "- Versions: "
        + ", ".join(f"{name} {version}" for name, version in versions.items())
    )
    print(
        f"- Data: {n_rows:,} rows ({args.entities} entities x {args.periods} periods x {args.versions} versions)"
    )
    print(
        f"- T = {T.isoformat()}; Q2 entity = {LOOKUP_ENTITY}; Q3 = {len(times)} decision times x {args.entities} entities"
    )
    print(
        f"- Timings: first run, then the median of {args.runs} warm runs, in milliseconds\n"
    )

    print("| Engine | Load + index (s) | Size on disk |")
    print("|---|---|---|")
    for engine, (seconds, size) in loads.items():
        print(f"| {engine} | {seconds:.2f} | {size} |")
    print()

    names = ["Q1", "Q1 (ASOF)", "Q2", "Q3"]
    print("| Engine | " + " | ".join(f"{n} first / warm" for n in names) + " |")
    print("|---|" + "---|" * len(names))
    for engine, by_query in timings.items():
        cells = [
            f"{by_query[n][0]:.1f} / {by_query[n][1]:.1f}" if n in by_query else "n/a"
            for n in names
        ]
        print(f"| {engine} | " + " | ".join(cells) + " |")
    print()

    reference = results["DuckDB table"]
    print("Results (count, sum of value; Q3 adds the number of non-null matches):\n")
    for name in names:
        print(f"- {name}: {reference[name]}")
    mismatches = [
        f"{engine} {name}: {result} != {reference['Q1' if name == 'Q1 (ASOF)' else name]}"
        for engine, by_query in results.items()
        for name, result in by_query.items()
        if result != reference["Q1" if name == "Q1 (ASOF)" else name]
    ]
    print(
        "\n"
        + (
            "All engines returned identical results."
            if not mismatches
            else "MISMATCHES:\n- " + "\n- ".join(mismatches)
        )
    )


if __name__ == "__main__":
    main()
