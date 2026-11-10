# Contributing to Quant Time Machine

Contributions to code, tests, documentation, research, and accessibility are welcome. Follow the [Code of Conduct](CODE_OF_CONDUCT.md). This is a CISC 498/499 capstone under active development; the [roadmap](../doc/roadmap.md) separates implemented work from planned features.

## Choose the right place

- Use [Discussions](https://github.com/nfiasco/Quant-Time-Machine/discussions) for setup questions, research questions, and early proposals. Read the [category guide](../doc/project/discussions.md).
- Use an [issue form](https://github.com/nfiasco/Quant-Time-Machine/issues/new/choose) for a reproducible bug or an agreed deliverable. Search existing issues and discussions first. Explain the affected behavior, a minimal reproduction, and the expected result; redact credentials and private or restricted data.
- Report vulnerabilities privately using [SECURITY.md](SECURITY.md), and accessibility barriers using [ACCESSIBILITY.md](ACCESSIBILITY.md).

Discuss substantial changes before implementing them. A focused maintenance change can go directly to a PR with `No issue: <specific reason>`; an extra tracking issue is not required.

## Set up a development environment

Install Git, Node.js 24 (see [.nvmrc](../.nvmrc)), and [uv](https://docs.astral.sh/uv/getting-started/installation/). uv installs the Python version in [backend/.python-version](../backend/.python-version). Clone the repository if you have write access, or fork it and clone your fork for an external contribution.

From the repository root, run each app in a separate terminal:

```sh
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

```sh
cd backend
uv sync --locked
cp .env.example .env
uv run fastapi dev
```

The frontend is at <http://localhost:3000>; the API documentation is at <http://localhost:8000/docs>. Environment files are optional for defaults; do not overwrite an existing local configuration. Running the apps and fixture tests needs no provider keys. Data endpoints need an ingested local store; follow the [backend guide](../backend/README.md#ingestion) when working on live data. Network and local-data tests are opt-in. Accounts and saved experiments are still planned; the sign-in forms do not establish an authenticated session.

## Development conventions

- Keep changes focused, and match the surrounding code and [.editorconfig](../.editorconfig). Prefer a reviewable PR; split independent work instead of imposing an arbitrary line limit.
- Python uses Ruff for linting, import ordering, and formatting. Frontend code follows [frontend/GUIDELINES.md](../frontend/GUIDELINES.md), uses TypeScript, and keeps API calls in `frontend/lib/api/`.
- Commit dependency manifests and lockfiles together. Use `npm install <package>` in `frontend/`, or `uv add <package>` / `uv add --dev <package>` in `backend/`. Routine installs use `npm ci` and `uv sync --locked`.
- Preserve the [time model](../doc/reference/time-model.md): eligibility depends on `available_at`, not just the observation date. Cover future-data exclusion, revisions, and time-zone boundaries when changing point-in-time behavior. Keep examples deterministic and use small fixtures.
- Follow the [accessibility checklist](ACCESSIBILITY.md#checking-a-change) for UI changes. Reuse the design tokens and existing components.
- Never commit credentials, `.env` files, raw provider downloads, local databases, or user data. `NEXT_PUBLIC_` values are public. Follow the [data-source terms](../doc/reference/data-sources.md); the MIT license does not grant rights to third-party datasets.
- Update the relevant API contract, README, or design document when behavior changes. Do not describe a planned capability as implemented.

## Validate a change

Run the checks for the components you change, from the repository root:

```sh
(cd frontend && npm run lint && npm test && npm run build)
(cd backend && uv run ruff check && uv run ruff format --check && uv run pytest)
python3 -m unittest discover -s .github/scripts -p 'test_*.py'
```

Backend fixture tests exclude `network` and `local_data` by default. Do not add provider credentials to CI or make default tests depend on live services. CI also builds the backend container and checks that it starts as a non-root user; Docker is not needed for ordinary local development. Explain checks that were not run and record actual results in the PR.

## Open and merge a pull request

1. Branch from current `main`, using a descriptive name such as `fix/snapshot-date-validation` or `docs/setup-guide`.
2. Fill in the PR template's **Summary**, **Linked work**, and **Validation** sections. Use `Refs #123` for partial work; use `Closes #123` only when all issue acceptance criteria are met.
3. Select one area label, one priority label, a primary milestone, and a responsible assignee. External contributors can ask a maintainer to set sidebar fields they cannot edit. See the [team workflow](../doc/project/github-workflow.md) for inherited defaults and the required PR metadata check.
4. Request a suitable teammate's review, respond to feedback, and resolve review conversations. CI, dependency review, and the metadata check must pass before merging. Maintainers triage security findings rather than dismissing them just to make a check green.

Maintainers apply the same CI and review expectations to dependency updates. Dependabot reports vulnerabilities but does not open update PRs; team members make and validate dependency changes themselves. Keep the manifest and lockfile consistent, include the advisory or release notes, and explain the relevant test results. Do not dismiss an alert simply to clear the queue.

Contributions are accepted under the repository's [MIT license](../LICENSE). Only contribute material you have permission to share, and retain required third-party notices.
