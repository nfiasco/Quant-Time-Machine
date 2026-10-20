# Quant Time Machine

AI-assisted quantitative research platform for point-in-time backtesting. Reconstructs what market data, SEC filings, fundamentals, and economic data were actually known at a historical date, helping researchers test strategies without look-ahead bias and produce reproducible results.

**Live site:** [quant-time-machine-uy5f.vercel.app](https://quant-time-machine-uy5f.vercel.app/)

> **Status:** Decisions and discovery (CISC 498, Fall 2026, milestone M1). The time model, data sources, and storage engine are written up in [`doc/`](doc/); the point-in-time data layer comes next. The roadmap is a draft, not a commitment.

## The problem

A backtest simulates how an investment strategy would have performed in the past. It's easy to let a backtest use information that wasn't available yet at the time. Common examples:

- a quarter's revenue used before the company published it
- economic data that was revised after its first release
- today's index membership applied to past years

This **look-ahead bias** makes strategies look better than they really were. Quant Time Machine aims to reconstruct the information that existed on any past date, so research questions like this one can be tested honestly:

> "Using only information available at the beginning of each month, test whether companies with improving revenue growth and positive momentum outperformed the market from 2010 to 2025."

The goal is not an AI that predicts stocks. It's a research environment where you can test investment ideas without accidentally "seeing the future."

## Repository structure

| Path                                       | What's there                                                                                         |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| [`frontend/`](frontend/)                   | Next.js web app (TypeScript, React, Tailwind CSS), deployed on Vercel                                |
| [`backend/`](backend/)                     | Python API (FastAPI), home of the point-in-time data layer and the backtester                        |
| [`backend/spikes/`](backend/spikes/)       | Sprint 1 experiments behind our data and storage decisions                                           |
| [`doc/`](doc/)                             | Project docs (see below)                                                                             |
| [`.github/`](.github/)                     | CI workflow, pull request template, and issue templates                                              |
| [`supabase/`](supabase/)                   | Supabase (PostgreSQL and Auth) config for user accounts and each user's saved data; no schema yet ([how it fits](doc/storage.md#two-stores-point-in-time-data-and-accounts)) |

Each app has its own README with more details. The main docs:

| Doc                                          | What it covers                                                                                          |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| [Roadmap and backlog](doc/roadmap.md)        | Requirements, milestones, sprints, every epic and story, risks, and the decision log                    |
| [Time model](doc/time-model.md)              | How "known at time *T*" works for every kind of data, with worked examples                              |
| [Data sources](doc/data-sources.md)          | Each data source's coverage, timestamps, limits, cost, and terms of use; known gaps; price-source choice |
| [Storage](doc/storage.md)                    | Why point-in-time data lives in Parquet files queried by DuckDB, with the benchmark                     |
| [API v1 contract](doc/api-v1.md)             | The `/v1` response envelope, errors, and example responses the frontend builds against                  |
| [Frontend guidelines](frontend/GUIDELINES.md) | The web app's design system, file structure, coding conventions, and rules for new pages                |

## Tech stack

| Area     | Tools                                                                                    |
| -------- | ---------------------------------------------------------------------------------------- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, shadcn/ui (Radix UI), Lucide icons, ESLint |
| Backend  | Python 3.14, FastAPI, uv (dependencies), pytest, Ruff (lint and format)                  |
| Data     | Point-in-time data: Parquet files queried with DuckDB, in-process ([decision D1](doc/storage.md)). Accounts and user data: Supabase (PostgreSQL and Auth) |
| Hosting  | Vercel (frontend); backend hosting not decided yet                                       |
| CI       | GitHub Actions                                                                           |

## Getting started

### Prerequisites

- [Git](https://git-scm.com/)
- [Node.js](https://nodejs.org/) 20.9 or newer. 24 LTS is recommended; `nvm use` picks it up from [`.nvmrc`](.nvmrc).
- [uv](https://docs.astral.sh/uv/getting-started/installation/), for example `brew install uv` on macOS. uv installs Python 3.14 automatically.

### Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

### Run the backend

```bash
cd backend
uv sync
uv run fastapi dev
```

Open http://localhost:8000/health, or the interactive API docs at http://localhost:8000/docs.

### Configuration and API keys

Running the apps and the tests needs no keys: tests use small fixtures, never live APIs. You need keys only to download data.

- **Backend:** copy [`backend/.env.example`](backend/.env.example) to `backend/.env` and fill it in. All settings load through one module, [`backend/app/config.py`](backend/app/config.py).
  - `FRED_API_KEY`: a free key from [FRED](https://fredaccount.stlouisfed.org/apikeys). Create a FRED account, then request a key; it's 32 lowercase letters and digits.
  - `SEC_USER_AGENT`: the SEC refuses automated requests that don't identify who's asking. Use your name or the project's name plus a contact email, for example `"Quant Time Machine (UD CISC 498) jdoe@udel.edu"`.
  - `TIINGO_API_KEY`: the token for daily prices (our price source, [decision D2](doc/data-sources.md#daily-prices-decision-d2)). Create a free [Tiingo](https://www.tiingo.com) account and copy the token from its [API token page](https://www.tiingo.com/account/api/token).
  - `DATA_DIR`: where downloaded data goes (default `backend/data/`, which git ignores).
  - `CORS_ORIGINS`: the web pages allowed to call the API from a browser, separated by commas (default `http://localhost:3000`). Add the deployed frontend's address here.
- **Frontend:** copy [`frontend/.env.example`](frontend/.env.example) to `frontend/.env.local`. `NEXT_PUBLIC_API_URL` is the backend's address (default `http://localhost:8000`). Anything starting with `NEXT_PUBLIC_` is visible in the browser, so never put a secret there.

Both `.env` files are git-ignored. Real environment variables override them, which is how a hosting provider supplies values.

### Run the same checks as CI

```bash
cd frontend && npm run lint && npm run build
```

```bash
cd backend && uv run ruff check && uv run ruff format --check && uv run pytest
```

## Deployment

The frontend is deployed on [Vercel](https://vercel.com):

1. In Vercel, choose **Add New → Project** and import this repository.
2. Set **Root Directory** to `frontend`. Vercel detects Next.js automatically, so no `vercel.json` is needed.
3. Deploy. Every push to `main` updates production, and every pull request gets its own preview URL.

Backend hosting isn't set up yet. Vercel can run the FastAPI app with no configuration, as a second Vercel project with Root Directory `backend`. Render, Railway, or Fly.io are also options if long-running backtests need them.

## Roadmap (draft)

The full plan, with requirements, milestones, sprints, and the epics, stories, and tasks for our GitHub Project board, is in [`doc/roadmap.md`](doc/roadmap.md). In short:

**CISC 498**

- Point-in-time dataset: historical prices, SEC filings and fundamentals, and vintage economic data
- Basic, deterministic backtesting engine
- Research API
- Web interface
- Accounts: sign in and keep your saved experiments and runs (Supabase)

**CISC 499**

- AI research assistant that turns questions into structured experiments, using MCP tools to get point-in-time data and run backtests
- Look-ahead-bias detection
- Experiment tracking, strategy comparison, and robustness testing

**Maybe later:** a desktop app. A mobile app is unlikely.

## Data policy

- **Raw datasets are never committed.** Everything downloaded from a data source goes under `DATA_DIR` (default `backend/data/`), which git ignores, along with local database files (`*.duckdb`). The only data in the repository is tiny test fixtures under `backend/tests/fixtures/`: synthetic values plus a few published figures, small enough to review.
- **Secrets are never committed.** Keys live in git-ignored `.env` files or in the hosting provider's settings, never in code, notebooks, or the browser bundle. If a key is ever committed, revoke it immediately: deleting it from a later commit doesn't remove it from history.
- **Each source's terms are followed.** That means the SEC's fair-access rules (at most 10 requests per second, with a declared User-Agent), FRED's API terms, and the license of whichever price source we use. We don't redistribute data the terms don't allow. Details are in [`doc/data-sources.md`](doc/data-sources.md).
- **Every stored fact records where it came from and when it became public.** Downloads keep their source URL and fetch time, so any number can be traced back. See the [time model](doc/time-model.md).

This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis. By using it, you agree to the [FRED® API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html).

## Contributing

How we work is described in [roadmap §6](doc/roadmap.md#6-running-the-project-board): the board, the working agreement, and the Definition of Ready and Done.

1. Pick up an issue from the board. New issues use the story, spike, or bug template in [`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/).
2. Create a branch from `main`, one story per branch (for example, `feature/s4-4-macro-as-of`).
3. Open a pull request that says `Closes #<issue>`. The [pull request template](.github/pull_request_template.md) includes the Definition of Done checklist; keep pull requests under about 400 changed lines.
4. Make sure CI passes and get a teammate's review before merging.

Never commit secrets or raw data (see the [data policy](#data-policy)).

## License

[MIT](LICENSE). Data from third-party sources keeps its own terms; see [`doc/data-sources.md`](doc/data-sources.md).

## Team

Ari, Elijah, Ian, Jacob, and Nico. CISC 498/499 senior capstone project.
