# Project documentation

Start with the [project README](../README.md#getting-started) to run the app, or the [contribution guide](../.github/CONTRIBUTING.md) to prepare a change. The [roadmap](roadmap.md) tracks requirements, milestones, and delivery status.

## Technical reference

- [Time model](reference/time-model.md): what was knowable at a given time, with worked examples.
- [Data sources](reference/data-sources.md): coverage, publication times, usage limits, and terms.
- [Storage](reference/storage.md): how Parquet, DuckDB, and Supabase fit together.
- [API v1 contract](reference/api-v1.md): request conventions, errors, and example responses.
- [Experiment spec v1 schema](reference/experiment-spec-v1.schema.json): the generated JSON Schema for backtest inputs.
- [Hosting](reference/hosting.md): deployment steps and the evidence behind the hosting decision.

## Project workflow

- [GitHub workflow](project/github-workflow.md): issue and PR metadata, project views, and automation.
- [GitHub settings](project/github-settings.md): repository checks and maintenance.
- [Discussions](project/discussions.md): where to ask questions and propose changes.
- [Contribution history](project/contribution-history.md): completed stories, contributors, and merged PR evidence.

## Research notes

- [Market data exploration notebook](research/market-data-exploration.ipynb): early experiments with yfinance and FRED, with follow-up corrections.
- [Database choice review](research/database-choice-review.md): alternatives considered and why the project kept its current storage design.
