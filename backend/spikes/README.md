# Spikes

Short, time-boxed experiments from Sprint 1 (milestone M1). Each script answers one question and prints a Markdown report; the findings and decisions are written up in [`doc/`](../../doc/). This is exploratory code, not part of the app: nothing in `app/` imports it, and the tests don't run it.

Each script declares its own pinned dependencies ([PEP 723](https://peps.python.org/pep-0723/) inline metadata), so `uv run` builds a throwaway environment for it and the backend's dependencies stay untouched. Scripts read keys from `backend/.env` (copy [`.env.example`](../.env.example)), never write into the repository, and never print keys.

Run them from `backend/`:

| Script | Story | Question | Needs | Command |
| --- | --- | --- | --- | --- |
| [`alfred.py`](alfred.py) | S4.1 | How do ALFRED vintages work, and what was known on a given day? | `FRED_API_KEY` | `uv run spikes/alfred.py` |
| [`edgar.py`](edgar.py) | S5.1 | Which EDGAR timestamp means "public", and what time zone is it in? | `SEC_USER_AGENT` | `uv run spikes/edgar.py` |
| [`prices.py`](prices.py) | S6.1 | Which daily price source gives raw prices, corporate actions, and delisted companies? | Optional: `TIINGO_API_KEY`, `ALPHAVANTAGE_API_KEY` | `uv run spikes/prices.py` |
| [`storage_benchmark.py`](storage_benchmark.py) | S3.2 | Which storage engine makes as-of queries simple and fast? | Nothing | `uv run --python 3.12 spikes/storage_benchmark.py` |

Notes:

- `storage_benchmark.py` runs on Python 3.12 because [pgserver](https://github.com/orm011/pgserver), which gives it a throwaway PostgreSQL server with nothing to install, has no 3.14 wheels yet. The `--python 3.12` flag is needed because `backend/.python-version` says 3.14. Pass `--postgres-dsn` to benchmark another PostgreSQL server instead.
- `prices.py` takes about two minutes because it waits between Alpha Vantage requests (the free tier allows 25 a day). Every script identifies itself honestly, and a source that blocks scripts is reported, not worked around.
- The SEC limits automated clients to 10 requests per second; `edgar.py` stays under that.
- Results are recorded, with the date they were retrieved, in [`doc/data-sources.md`](../../doc/data-sources.md) and [`doc/storage.md`](../../doc/storage.md).
