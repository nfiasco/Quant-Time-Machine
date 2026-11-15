# Run records, determinism, and the audit

> **Story S7.7.** Version 1, 2026-11-12. To change what a run saves, update [`app/backtest/records.py`](../../backend/app/backtest/records.py), [`app/backtest/audit.py`](../../backend/app/backtest/audit.py), [`app/backtest/canonical.py`](../../backend/app/backtest/canonical.py), their tests, and this page together.

Every run saves a record: a folder of JSON files that say exactly what it used and what it produced. A reviewer can read them, check them, and run the same thing again.

```bash
cd backend
uv run python -m app.runs tests/fixtures/specs/canonical.json
```

```python
from app.backtest.spec import parse_spec
from app.config import get_settings
from app.runs import run_backtest

saved = run_backtest(parse_spec(text), get_settings())
saved.record.run_id  # names the spec, the data version, and the engine version
saved.folder  # DATA_DIR/runs/<run ID>/
```

- **The same inputs give the same bytes.** The same spec, data version, and engine version always produce the same run ID and the same files, byte for byte.
- **A run is pinned to a data version** ([`app/data/versions.py`](../../backend/app/data/versions.py)): the store's newest, unless `--data-version` names another. A run that read the whole store can't be recorded.
- **No file holds a price.** As everywhere in the engine, results are weights, returns, and dates: Tiingo's prices are for internal use only (D2).

## What a run saves

Runs live in `DATA_DIR/runs/`, one folder for each run ID.

| File | What it holds |
| --- | --- |
| `run.json` | The run ID, the spec exactly as it ran, its hash, the data version, the engine version, the git SHA, and each other file's size and SHA-256 |
| `returns.json` | `periods`: each holding period's decision and fill times, where it ends, the universe's size, turnover, cost, gross and net returns, the benchmark's return, the risk-free rate, and the portfolio's value. `equity_curve`: the portfolio's value beside the benchmark's |
| `holdings.json` | Each holding of each period: its weight, its signals' values at the decision, its return, and where it was valued |
| `trades.json` | Each trade: its fill, its weight before and after, the value traded, and its cost |
| `metrics.json` | The run's [metrics](metrics.md) |
| `warnings.json` | Each gap in the data, and what the run assumed instead |
| `audit.json` | [What each view the run opened read](#the-audit), and when the newest of it became known |

Every holding, trade, and warning carries `decision`, the New York day of its decision, so the files join on it. Times are in UTC, as `2020-06-01T13:30:00Z`. The API will show them in New York time, as it does everywhere (D12).

`run.json` for the canonical spec from 2020 to 2022, with the spec and four of the files left out:

```json
{
  "data_version": "20261111T030742Z",
  "engine_version": "1.0.0",
  "files": {
    "audit.json": {
      "bytes": 1652696,
      "sha256": "…"
    },
    "metrics.json": {
      "bytes": 641,
      "sha256": "…"
    }
  },
  "git_sha": "…",
  "record_version": 1,
  "run_id": "9dfedcfa918368dcbd3d3af6d83abe4496f4ea6ed475303da691b5b1dcb2b30f",
  "spec": {},
  "spec_hash": "f62a573942cd9cea91535597a86307047874cf788c5639040e2e5b9ed7298102"
}
```

**What isn't saved, on purpose:** when the run happened, and how long it took. Either would make two runs of the same inputs differ. The run registry will keep them beside the files (S13.1).

## The run ID and the spec hash

- **The spec hash** is the SHA-256 of the spec's [canonical JSON](#canonical-json). It hashes the validated spec, not the text it came from. So the order of its keys, its spacing, `10` against `10.0`, and whether a default such as `"rank": null` was written out don't change it. The order of a list, such as the filters, does, and so does the spec's `name`.
- **The run ID** is the SHA-256 of the canonical JSON of three things:

  ```json
  {"data_version":"20261111T030742Z","engine_version":"1.0.0","spec":{}}
  ```

  It's all 64 hex digits. The same three always give the same ID, so a run ID names its inputs, not the moment it ran.
- **The engine version** is `ENGINE_VERSION` in [`app/backtest/__init__.py`](../../backend/app/backtest/__init__.py). Raise it with any change that can change a saved result: to a signal, the portfolio, returns, metrics, or the loop, or to how `app/data` reads the store, such as how a quarter is derived.
- **The git SHA** is recorded and isn't part of the ID. It's the `GIT_SHA` setting if there is one (Railway sets `RAILWAY_GIT_COMMIT_SHA` on a deploy from GitHub), or else git's HEAD, with `-dirty` after it when tracked files have uncommitted changes. It's `null` where neither is known. The commit also pins every dependency, through `uv.lock`.
- **The record version**, `record_version`, is the version of the files' layout. It isn't part of the ID either: a new layout says the same things about the same run.

## Canonical JSON

[`canonical_json`](../../backend/app/backtest/canonical.py) writes a value one way only:

- An object's keys are sorted, at every level.
- The text is UTF-8, and characters are written as themselves, not as `\u` escapes.
- A number is the shortest text that reads back as the same float, as Python writes it: `0.1`, `1e-07`, `1.5e+16`. A whole float keeps its `.0`, an integer has none, and `-0.0` is written `0.0`.
- NaN and the infinities aren't JSON, and are rejected.

Hashes use the compact form, with no spaces. Files use the same text indented by two spaces, with a newline at the end, so two runs can be compared line by line with `diff`.

**Numbers are rounded before they're saved.** Every computed number in `returns.json`, `holdings.json`, `trades.json`, and `metrics.json` keeps 12 significant digits. A float has 15 to 17, and the last one or two are where machines differ: CAGR is a power, and a power's last digit depends on the machine's maths library. The spec is never rounded. It's saved exactly as it ran, or the saved spec wouldn't be the one to run again.

## The audit

Every row a `PointInTimeView` returns goes in its access log ([`app/data/view.py`](../../backend/app/data/view.py)). The loop opens a view for each decision, bound to the decision's time, so the log is the list of everything that decision could have used.

One decision of the canonical spec reads about 17,700 rows: 9,300 price bars, 8,200 XBRL facts, and the rest identities, memberships, corporate actions, and the risk-free rate. From 2010 to 2025 that's about 3 million. So the loop summarizes each view's log as the view closes and keeps the summary, not the rows. For that whole period, `audit.json` is 8.7 MB of the run's 10.9 MB: 385 views, and 37,377 groups.

`audit.json` has one entry for each view the run opened, in order:

| `purpose` | Bound to | What's read through it |
| --- | --- | --- |
| `decision` | The decision's time, 09:30 ET by default | The universe's members, each signal's inputs, the benchmark's identity, and the risk-free rate |
| `fill` | The close of the decision's fill session | The bars that value the period that ends there, and that say which of the decision's choices can fill |
| `end` | The close of the run's last session | The bars that value the last period |

An entry has its `decision` (the New York day), its `knowledge_time`, its `rows`, and for each table it read:

- `rows`: how many distinct rows. A row read twice, as the revenue facts are by `rev_growth` and `rev_accel`, counts once.
- `earliest_available_at` and `latest_available_at`: when the oldest and the newest of them became known.
- `sha256`: [a hash of every row](#checking-a-hash).
- `groups`: the rows by the table's first key column, each with its `rows` and its newest row's `available_at` and `source_ref`.

| Table | A group is | Its `latest_source_ref` is |
| --- | --- | --- |
| `price_bars`, `corporate_actions` | A security | The newest bar or action read |
| `xbrl_facts` | A company, by CIK | The accession number of the last filing known |
| `macro_observations` | A series | The vintage read |
| `securities` | A security | Where its identity comes from |
| `universe_members` | A universe | The newest change to its members |

From the June 1, 2020 decision of the canonical spec, on data version 20261111T030742Z:

```json
{
  "decision": "2020-06-01",
  "knowledge_time": "2020-06-01T13:30:00Z",
  "purpose": "decision",
  "rows": 17732,
  "tables": [
    {
      "table": "macro_observations",
      "rows": 1,
      "groups": [
        {
          "key": "TB3MS",
          "latest_available_at": "2020-05-01T20:15:00Z",
          "latest_source_ref": "TB3MS vintage 2020-05-01",
          "rows": 1
        }
      ]
    },
    {
      "table": "xbrl_facts",
      "rows": 8249,
      "latest_available_at": "2020-05-26T23:59:23Z",
      "groups": [
        {
          "key": 320193,
          "latest_available_at": "2020-04-30T22:03:10Z",
          "latest_source_ref": "0000320193-20-000052",
          "rows": 248
        }
      ]
    }
  ]
}
```

(Shortened: four tables, 40 companies, and each table's hash are left out, and the keys are reordered to read more easily.) CIK 320193 is Apple, and `0000320193-20-000052` is its 10-Q for the quarter that ended in March 2020, accepted at 18:03 ET on April 30. That's the latest filing `get_latest_filing_as_of("AAPL")` gives at the same moment. Apple's newest bar is April 30's: 12-1 momentum skips May.

**What the audit proves.** On every entry, each table's `latest_available_at` is at or before the entry's `knowledge_time`, so nothing a decision read was known after it. Since that holds for the newest row, it holds for them all. S12.1 will check it on every run and show the result. A fill's view is bound to the fill session's close, after its decision, because a fill's price isn't known until then ([time model](time-model.md), rules 4 and 10).

**What it leaves out.** The rows themselves. A table's hash says a later run read exactly the same ones, and the groups say which filing, release, or bar was each one's newest. To see every row, run the decision again: the same data version gives the same rows.

### Checking a hash

A table's `sha256` covers every distinct row the view returned from it:

1. Write each row as the canonical JSON of a list: its key's values, in the order [`app/data/tables.py`](../../backend/app/data/tables.py) lists them, then its `available_at`, then its `source_ref`. Dates are written as `2020-04-01`, and times in UTC.

   ```json
   ["TB3MS","2020-04-01","2020-05-01T20:15:00Z","TB3MS vintage 2020-05-01"]
   ```

2. Sort the lines, join them with newlines, and take the SHA-256 of the UTF-8 text.

The order the rows were read in doesn't matter, which it must not: the store returns rows that tie in any order. `row_line` and `rows_hash` in [`audit.py`](../../backend/app/backtest/audit.py) do both steps.

## Determinism

**The promise.** The same spec, data version, and engine version give the same run ID and byte-identical files (FR-B3, NFR-2).

**What makes it hold:**

- Every read is pinned to a data version, whose files never change ([`versions.py`](../../backend/app/data/versions.py)).
- The engine only reads through views, never the clock or the network, and has no randomness.
- Holdings, trades, and warnings are in a fixed order, and the audit doesn't depend on the order of reads.
- The files are canonical JSON, their numbers are rounded, and none has a time of day in it.

**How it's checked**, in CI on every pull request ([`tests/test_records.py`](../../backend/tests/test_records.py)):

- `test_the_same_inputs_give_byte_identical_files` runs a spec twice in one process and compares every byte.
- `test_two_processes_give_byte_identical_files` runs the command in two fresh processes with different hash seeds. Python orders a set of strings differently in each process, so anything that leaned on that order would differ between them, though never within one.
- `test_a_pinned_runs_files_never_change` has a toy run's ID and file hashes written into the test. A laptop and CI's Linux must both produce them, and a change to the engine that changes a result fails it until `ENGINE_VERSION` is raised.

### Saving a run that's already saved

A run ID names its inputs, so saving the same run again finds its folder there.

- **The same results:** the folder is left as it is, with the git SHA that first wrote it.
- **Different results:** the same inputs gave two answers, which means the engine changed without a new `ENGINE_VERSION`. `write_run` raises `RunConflictError`, which names the files that differ. Raise the version, or replace the saved run with `--overwrite`.

A folder is written whole or not at all: the files are written beside it, then moved into place.

## Known limitations

- **Rounding can't cover every case.** If two machines' results straddle a rounding boundary, their 12th digits differ. None has been seen, and the pinned test would show one.
- **The pinned hashes were produced on macOS.** CI's Linux run is the first check that another machine agrees.
- **The audit is a summary.** It proves the timing of every row and names each group's newest source, but it doesn't list the rows.
- **The audit covers what views returned.** The catalogs' coverage reads return date ranges, not rows, and aren't logged. The engine doesn't use them.
- **A `-dirty` git SHA** says the code had uncommitted changes, not what they were.
- **Runs aren't tied to a user yet,** and two people who run the same spec on the same data share one folder. Accounts and the run registry come with S13.1.
- **The deployed server can't save runs yet.** Its user can only read the volume ([hosting](hosting.md)), so S8.4 needs a folder it can write to.
- **Re-running needs the data version's files.** Deleting a table to rebuild it breaks every run pinned to a version that lists its files ([database choice review](../research/database-choice-review.md)).
