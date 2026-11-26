# Quant Time Machine — Frontend

The Quant Time Machine web app, built with [Next.js](https://nextjs.org) (App Router), React, TypeScript, [Tailwind CSS](https://tailwindcss.com), and [shadcn/ui](https://ui.shadcn.com) components on [Radix UI](https://www.radix-ui.com). It was bootstrapped with the official [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app) starter.

**Before your first frontend pull request, read [`GUIDELINES.md`](GUIDELINES.md):** the design system, where code goes, and the rules reviewers check.

## Getting started

Requires Node.js 20.9+ (24 LTS recommended; see [`../.nvmrc`](../.nvmrc)).

```bash
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Pages auto-update as you edit files.

## Landing page

The homepage (`/`, code in [`features/landing/`](features/landing)) is a scroll story. The logo, a counter-clockwise arrow, unwinds into a timeline of what was public before June 5, 2020, 9:30 AM ET. Each stop becomes known as the arrow reaches it, and at the knowledge time the page shows the snapshot that moment returns. The line then winds back into the logo, ending on **Enter workspace** (`/dashboard`) and **Create account**. Below the story are the features and the API.

- **Real facts.** Every date and value comes from the snapshot golden test (`backend/tests/test_api_snapshot.py`) and is listed in [`story/events.ts`](features/landing/story/events.ts). The ticker wall behind the logo is decoration: its tickers are real, its numbers are random, and the footer says so.
- **Motion.** [GSAP](https://gsap.com) ScrollTrigger scrubs one timeline over a sticky stage; [Lenis](https://lenis.darkroom.engineering) smooths wheel scrolling. Both load only in the browser and only when motion is allowed. With reduced motion (or no JavaScript), the same content renders as a static page. Pacing lives in [`story/beats.ts`](features/landing/story/beats.ts).
- **Look.** Neutral black and white with one accent, terminal amber, in both themes: the same palette as the workspace (`app/globals.css`, GUIDELINES.md §3).

The page makes no API calls and needs no keys. See [S9.8](../doc/roadmap.md#s98-public-landing-page) for delivery evidence.

## Time Machine

The explorer (`/time-machine`, code in [`features/time-machine/`](features/time-machine)) shows what was known at a moment and what wasn't yet, for up to 10 companies and 10 economic series (S9.2). It renders `GET /v1/snapshot` as one knowledge horizon per company and per series.

- **The URL is the view.** `/time-machine?as_of=2020-06-05T09:30&tickers=AAPL,TSLA&series=UNRATE,FEDFUNDS` reproduces roadmap §2.3, and any view can be shared by its link. `as_of` is New York time without an offset; a date alone means 09:30 ET. [`params.ts`](features/time-machine/params.ts) parses and builds these links.
- **Fetched on the server.** The page asks the API from the Next.js server, so the API's CORS list doesn't matter, but `NEXT_PUBLIC_API_URL` must be set for every Vercel environment that should work (Preview included).
- **No future record on the known side.** [`snapshot-events.ts`](features/time-machine/snapshot-events.ts) decides each record's side from its own `available_at`, and leaves out (and counts) any record the API put on the wrong side. Its tests run on the API's own §2.3 example.
- **States.** A link with no moment shows how to start; a moment alone offers a starter selection; a problem in the link or an API error shows next to the field it concerns; an unreachable API shows a retry. While a new view loads, the old one dims.

## Backtest builder

The builder (`/backtests/new`, code in [`features/backtests/`](features/backtests)) builds an experiment spec with a form and runs it (S9.5). A run's page, `/backtests/<run_id>`, shows its progress, and then [its results](#backtest-results).

- **Fields from the catalogs.** Each signal's parameters come from its kind's JSON Schema in `GET /v1/catalog/signals`, and a macro signal's series from `/v1/catalog/series`, both loaded on the server. The form edits a draft ([`draft.ts`](features/backtests/draft.ts)), so a signal can be renamed without losing the filters on it.
- **Errors where they belong.** The form checks what it can as you type ([`validation.ts`](features/backtests/validation.ts)), and the API's 422 paths, such as `signals.mom_12_1.skip_months`, land beside the same fields ([`field-errors.ts`](features/backtests/field-errors.ts)).
- **Running.** Run sends the spec through a Server Action ([`actions.ts`](features/backtests/actions.ts)), which opens the run's page: at once for a spec that already ran on the newest data, and otherwise to watch it go. That page reads the run on the server and refreshes itself every 2 seconds until it has finished ([`run-refresher.tsx`](features/backtests/run-refresher.tsx)).
- **Starting points.** `?preset=canonical` opens the canonical example, and `?from=<run_id>` an earlier run's spec, which is where "Edit and run again" goes. "Reset to the example" returns to the example.
- **Locally,** runs need the backend (`cd backend && uv run fastapi dev`) and its store. A new run of the canonical spec for 2020 to 2022 takes about 40 seconds. The deployed API can't take runs until its run folder is writable (S8.4).

## Backtest results

Once a run has succeeded, its page, `/backtests/<run_id>`, is its results (S9.6): the evidence behind the numbers as well as the numbers. [`run-results.tsx`](features/backtests/run-results.tsx) puts it together from the run and what [`results-data.ts`](features/backtests/results-data.ts) reads beside it, all on the server.

- **Assumptions and warnings first.** The decision time, fill rule, costs, delisting return, benchmark, universe, and data version, and what every run assumes ([`assumptions.ts`](features/backtests/assumptions.ts)); then the run's warnings by kind, each linking to its rebalance, and its coverage report ([`warnings.ts`](features/backtests/warnings.ts)).
- **The curve and the metrics.** The growth of $1 beside the benchmark, and both drawdowns, drawn from the API's equity curve ([`equity.ts`](features/backtests/equity.ts)) with Recharts through shadcn's `chart` (decision D8). The strategy is a solid line and the benchmark a dashed one, and the same numbers are in words and in a table. Every metric is in [`metric-rows.ts`](features/backtests/metric-rows.ts), with what it measures.
- **One rebalance at a time.** `?decision=2020-06-01`, the API's own name, picks the rebalance; without it, the last one ([`decisions.ts`](features/backtests/decisions.ts)). Its period, every member of the universe, held or not and why, from `GET /v1/backtests/{run_id}/members` ([`members.ts`](features/backtests/members.ts)), its trades, and its audit: each view's knowledge time T and every table it read, with when its rows became public, one step from their source ([`audit.ts`](features/backtests/audit.ts)). The newest filing each company's facts came from sits on its row, so "why didn't June 1, 2020 buy Apple, and which filing told it so?" is answered in one place.
- **States.** A run saved before engine 1.1.0 has no coverage report, and one saved before record version 3 no members record: the page says so and lists the holdings. A part the API couldn't give shows its own error with a retry, and while another rebalance loads, the old one dims.

## Configuration

Copy [`.env.example`](.env.example) to `.env.local` (git-ignored):

| Variable              | Default                 | What it is                                   |
| --------------------- | ----------------------- | -------------------------------------------- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base URL of the backend API (see `backend/`) |
| `NEXT_PUBLIC_SUPABASE_URL` | unset | Supabase project origin |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | unset | Public publishable or legacy anon key |
| `SITE_URL` | localhost in dev | Server-only trusted frontend origin for email links |

Read it only through [`lib/api/client.ts`](lib/api/client.ts) (`API_URL`, `apiUrl("/health")`, `apiFetch`). The dashboard shows whether the API is reachable; with the backend running (`cd backend && uv run fastapi dev`), it says "API online". Next.js copies `NEXT_PUBLIC_` values into the JavaScript sent to browsers when the app is built, so:

- never put a secret in one;
- restart `npm run dev` after changing one;
- in Vercel, set it per environment (Production, Preview), because the value is frozen into each deployment when it's built. Production is set to the deployed API, `https://quant-time-machine-api.up.railway.app` (S15.1). Preview isn't set, so previews use the default; the API's CORS allows only production and `localhost:3000`.

## Accounts (S16.1 / S16.3 / S16.4)

Email/password sign-up, sign-in, sign-out, email confirmation, and password recovery use Supabase Auth. Copy the auth placeholders in `.env.example` to an ignored `.env.local`. Set the project URL, public publishable/anon key, and trusted `SITE_URL`; configure the hosted redirect allow-list and email delivery as described in [`../supabase/README.md`](../supabase/README.md). Missing configuration shows **Accounts unavailable**. No service-role key is used.

Sessions persist in server-managed HttpOnly cookies across reloads. The header shows the verified email and a sign-out action. `/experiments` requires sign-in and preserves its return destination; public research pages remain available. The Experiments page also forwards its access token on the server to FastAPI `/v1/me` and checks the verified subject; run the backend with `SUPABASE_URL` set to the same project. The token never reaches a Client Component, and identity responses are not cached. Saved experiments and RLS user-data tables remain separate stories. The auth smoke tests use the real Supabase SSR client with synthetic HTTP responses, so default tests need no account or network access.

## Scripts

| Command                   | What it does                                                 |
| ------------------------- | ------------------------------------------------------------ |
| `npm run dev`             | Start the dev server on port 3000                            |
| `npm run build`           | Production build (also type-checks the project)              |
| `npm run start`           | Serve the production build (run `build` first)               |
| `npm run lint`            | Lint with ESLint                                             |
| `npm run format`          | Format the code with Prettier                                |
| `npm run format:check`    | Check the formatting without changing files (CI runs it)     |
| `npm test`                | Run the unit tests once with Vitest                          |
| `npm run api:types`       | Regenerate `lib/api/schema.ts` from the API's OpenAPI schema |
| `npm run api:types:check` | Check that it's current (CI runs it)                         |

## Project structure

```
app/                      # Routing only: layouts, pages, loading/error/not-found
├── layout.tsx            # Root layout: <html>, fonts (Geist), theme script, title template
├── globals.css           # Tailwind, design tokens (light and dark), global utilities
├── page.tsx              # Public landing page (/)
├── not-found.tsx         # 404 page
├── (app)/                # Pages inside the app shell (URLs don't include "(app)")
│   ├── layout.tsx        # Sidebar, header, footer
│   ├── loading.tsx       # Shared loading skeleton
│   ├── error.tsx         # Shared error boundary
│   ├── dashboard/       # Dashboard (/dashboard)
│   └── time-machine/, backtests/, backtests/new/, backtests/[runId]/, revisions/, filings/,
│       experiments/, methodology/, privacy/, assistant/, compare/
└── (auth)/               # Sign-in, sign-up, and password recovery, without the app shell
components/
├── ui/                   # shadcn/ui primitives (generated, then owned by us)
├── layout/               # App shell: sidebar, header, footer, page header, theme toggle
└── feedback/             # Shared states: planned page, error state
features/                 # One folder per feature: its components, data, actions
├── landing/              # The public landing page and its scroll story
├── dashboard/
├── time-machine/
├── backtests/
└── auth/
config/
├── site.ts               # Name, links, required notices
└── navigation.ts         # Every route: title, icon, status, roadmap story
hooks/                    # Shared React hooks
lib/
├── api/                  # Backend client: client.ts (API_URL, apiFetch), schema.ts (generated), types.ts, errors.ts, one file per endpoint group
├── time.ts               # Market-time (ET) parsing and formatting
├── format.ts             # Number formatting (prices, revenue, macro values)
├── theme.ts              # Light and dark theme helpers
└── utils.ts              # cn() for merging class names
components.json           # shadcn/ui CLI settings
GUIDELINES.md             # Design system, conventions, and project rules
```

Pages that aren't built yet are placeholders: each shows what it will do and which roadmap story and milestone deliver it. All of that comes from [`config/navigation.ts`](config/navigation.ts).

### Adding a page

1. Add it to `routes` in [`config/navigation.ts`](config/navigation.ts) (and to `navSections` if it belongs in the sidebar).
2. Create `app/(app)/<path>/page.tsx` that exports `metadata = routeMetadata(routes.<name>)` and renders `PlannedPage` or the real UI.
3. Put the feature's code in `features/<name>/`.

Links are type-checked (`typedRoutes`), so a link to a page that doesn't exist fails the build. See [`GUIDELINES.md` §11](GUIDELINES.md#11-adding-a-page) for the full checklist.

### Adding a UI component

From `frontend/`, add components from shadcn/ui, for example:

```bash
npx shadcn@latest add tabs
```

They land in `components/ui/` and use our theme automatically. See [`GUIDELINES.md` §5](GUIDELINES.md#5-components).

Static files like images go in a `public/` folder (create it when needed).

`AGENTS.md` and `CLAUDE.md` were generated by `create-next-app`. They point AI coding assistants to the Next.js docs bundled in `node_modules/next/dist/docs/`, which match the installed version. `next dev` rewrites only the block between the `nextjs-agent-rules` markers; the project rules below it are ours. Keep both files committed.

## Deployment (Vercel)

1. In Vercel, choose **Add New → Project** and import this GitHub repository.
2. Set **Root Directory** to `frontend`. Vercel detects Next.js automatically, so no `vercel.json` is needed.
3. Deploy. Every pull request then gets its own preview URL.

## Learn more

- [Next.js documentation](https://nextjs.org/docs)
- [Learn Next.js](https://nextjs.org/learn), an interactive tutorial
- [Tailwind CSS documentation](https://tailwindcss.com/docs)
- [shadcn/ui documentation](https://ui.shadcn.com/docs)
