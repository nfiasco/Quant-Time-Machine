# Quant Time Machine

AI-assisted quantitative research platform for point-in-time backtesting. Reconstructs what market data, SEC filings, fundamentals, and economic data were actually known at a historical date, helping researchers test strategies without look-ahead bias and produce reproducible results.

> **Status:** Early setup (CISC 498, Fall 2026). The scope is still being defined, and the roadmap below is a draft, not a commitment.

## The problem

A backtest simulates how an investment strategy would have performed in the past. It's easy to let a backtest use information that wasn't available yet at the time. Common examples:

- a quarter's revenue used before the company published it
- economic data that was revised after its first release
- today's index membership applied to past years

This **look-ahead bias** makes strategies look better than they really were. Quant Time Machine aims to reconstruct the information that existed on any past date, so research questions like this one can be tested honestly:

> "Using only information available at the beginning of each month, test whether companies with improving revenue growth and positive momentum outperformed the market from 2010 to 2025."

The goal is not an AI that predicts stocks. It's a research environment where you can test investment ideas without accidentally "seeing the future."

## Repository structure

| Path                                       | What's there                                                                  |
| ------------------------------------------ | ----------------------------------------------------------------------------- |
| [`frontend/`](frontend/)                   | Next.js web app (TypeScript, React, Tailwind CSS), deployed on Vercel         |
| [`backend/`](backend/)                     | Python API (FastAPI), home of the point-in-time data layer and the backtester |
| [`.github/workflows/`](.github/workflows/) | CI: lints, builds, and tests both apps on every pull request                  |

Each app has its own README with more details.

## Tech stack

| Area     | Tools                                                                     |
| -------- | ------------------------------------------------------------------------- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, ESLint     |
| Backend  | Python 3.14, FastAPI, uv (dependencies), pytest, Ruff (lint and format)   |
| Hosting  | Vercel (frontend); backend hosting not decided yet                        |
| CI       | GitHub Actions                                                            |

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

**CISC 498**

- Point-in-time dataset: historical prices, SEC filings and fundamentals, and vintage economic data
- Basic, deterministic backtesting engine
- Research API
- Web interface

**CISC 499**

- AI research assistant that turns questions into structured experiments, using MCP tools to get point-in-time data and run backtests
- Look-ahead-bias detection
- Experiment tracking, strategy comparison, and robustness testing

**Maybe later:** a desktop app. A mobile app is unlikely.

## Contributing

1. Create a branch from `main` (for example, `feature/price-loader`).
2. Commit your changes and open a pull request.
3. Make sure CI passes and get a teammate's review before merging.

Never commit secrets. Put API keys in a local `.env` file, which git ignores.

## Team

Ari, Elijah, Ian, Jacob, and Nico. CISC 498/499 senior capstone project.
