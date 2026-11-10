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

The page makes no API calls and needs no keys.

## Time Machine

The explorer (`/time-machine`, code in [`features/time-machine/`](features/time-machine)) shows what was known at a moment and what wasn't yet, for up to 10 companies and 10 economic series (S9.2). It renders `GET /v1/snapshot` as one knowledge horizon per company and per series.

- **The URL is the view.** `/time-machine?as_of=2020-06-05T09:30&tickers=AAPL,TSLA&series=UNRATE,FEDFUNDS` reproduces roadmap §2.3, and any view can be shared by its link. `as_of` is New York time without an offset; a date alone means 09:30 ET. [`params.ts`](features/time-machine/params.ts) parses and builds these links.
- **Fetched on the server.** The page asks the API from the Next.js server, so the API's CORS list doesn't matter, but `NEXT_PUBLIC_API_URL` must be set for every Vercel environment that should work (Preview included).
- **No future record on the known side.** [`snapshot-events.ts`](features/time-machine/snapshot-events.ts) decides each record's side from its own `available_at`, and leaves out (and counts) any record the API put on the wrong side. Its tests run on the API's own §2.3 example.
- **States.** A link with no moment shows how to start; a moment alone offers a starter selection; a problem in the link or an API error shows next to the field it concerns; an unreachable API shows a retry. While a new view loads, the old one dims.

## Configuration

Copy [`.env.example`](.env.example) to `.env.local` (git-ignored):

| Variable              | Default                 | What it is                                   |
| --------------------- | ----------------------- | -------------------------------------------- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base URL of the backend API (see `backend/`) |

Read it only through [`lib/api/client.ts`](lib/api/client.ts) (`API_URL`, `apiUrl("/health")`, `apiFetch`). The dashboard shows whether the API is reachable; with the backend running (`cd backend && uv run fastapi dev`), it says "API online". Next.js copies `NEXT_PUBLIC_` values into the JavaScript sent to browsers when the app is built, so:

- never put a secret in one;
- restart `npm run dev` after changing one;
- in Vercel, set it per environment (Production, Preview), because the value is frozen into each deployment when it's built. Production is set to the deployed API, `https://quant-time-machine-api.up.railway.app` (S15.1). Preview isn't set, so previews use the default; the API's CORS allows only production and `localhost:3000`.

## Scripts

| Command         | What it does                                          |
| --------------- | ----------------------------------------------------- |
| `npm run dev`   | Start the dev server on port 3000                     |
| `npm run build` | Production build (also type-checks the project)       |
| `npm run start` | Serve the production build (run `build` first)        |
| `npm run lint`  | Lint with ESLint                                      |
| `npm test`      | Run the unit tests once with Vitest                   |

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
│   └── time-machine/, backtests/, backtests/new/, revisions/, filings/,
│       experiments/, methodology/, privacy/, assistant/, compare/
└── (auth)/               # Sign-in and sign-up, without the app shell
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
├── api/                  # Backend client: client.ts (API_URL, apiFetch), types.ts, errors.ts, one file per endpoint group
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
