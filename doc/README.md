# Project documentation

Start with the [project README](../README.md#getting-started) to run the app, or the [contribution guide](../.github/CONTRIBUTING.md) to prepare a change. The [roadmap](roadmap.md) tracks requirements, milestones, and delivery status.

## Technical reference

- [Time model](reference/time-model.md): what was knowable at a given time, with worked examples.
- [Data sources](reference/data-sources.md): coverage, publication times, usage limits, and terms.
- [Storage](reference/storage.md): how Parquet, DuckDB, and Supabase fit together.
- [API v1 contract](reference/api-v1.md): request conventions, errors, caching, and example responses, for the as-of endpoints and for submitting and reading backtests.
- [OpenAPI schema](reference/openapi.json): the generated schema the API serves at `/openapi.json`, from which the frontend's TypeScript types are generated.
- [Experiment spec v1 schema](reference/experiment-spec-v1.schema.json): the generated JSON Schema for backtest inputs.
- [Signal library](reference/signals.md): each backtest signal's formula, data, minimum history, and the reasons it can have no value.
- [Portfolio construction and costs](reference/portfolio.md): how filters, a ranking, and weights turn signals into a portfolio, long only or long-short, and what trading it costs.
- [Performance metrics and the benchmark](reference/metrics.md): each metric's formula, the risk-free rate a decision knew, when a metric has no value, and a run worked by hand.
- [Run records, determinism, and the audit](reference/runs.md): the files a run saves, its run ID, canonical JSON, what each decision read, how byte-identical results are checked, and how the API runs one in the background.
- [Hosting](reference/hosting.md): deployment steps and the evidence behind the hosting decision.

## Project workflow

- [GitHub workflow](project/github-workflow.md): issue and PR metadata, project views, and automation.
- [GitHub settings](project/github-settings.md): repository checks and maintenance.
- [Discussions](project/discussions.md): where to ask questions and propose changes.
- [Contribution history](project/contribution-history.md): completed stories, contributors, and merged PR evidence.
- [Planning record](project/planning.md): scope decisions, owners, and carry-over from each sprint planning.

## Research notes

- [The canonical backtest, 2010 to 2025](research/canonical-backtest.md): the revenue-growth-plus-momentum question run end to end, its warnings and sanity checks, how far to trust the result, and the demo's middle section.
- [How existing tools answer the canonical question](research/existing-tools.md): a pandas notebook and backtrader tried hands-on, QuantConnect and WRDS from their documentation, and what a naive notebook gets wrong.
- [Success measures and evaluation plan](research/evaluation-plan.md): the project's success measures, the research-effort baseline, and the usability-test protocol.
- [Market data exploration notebook](research/market-data-exploration.ipynb): early experiments with yfinance and FRED, with follow-up corrections.
- [Database choice review](research/database-choice-review.md): alternatives considered and why the project kept its current storage design.
