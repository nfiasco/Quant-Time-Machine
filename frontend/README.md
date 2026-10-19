# Quant Time Machine — Frontend

The Quant Time Machine web app, built with [Next.js](https://nextjs.org) (App Router), React, TypeScript, [Tailwind CSS](https://tailwindcss.com), and [shadcn/ui](https://ui.shadcn.com) components on [Radix UI](https://www.radix-ui.com). It was bootstrapped with the official [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app) starter.

**Before your first frontend pull request, read [`GUIDELINES.md`](GUIDELINES.md):** the design system, where code goes, and the rules reviewers check.

## Getting started

Requires Node.js 20.9+ (24 LTS recommended; see [`../.nvmrc`](../.nvmrc)).

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Pages auto-update as you edit files.

## Configuration

Copy [`.env.example`](.env.example) to `.env.local` (git-ignored):

| Variable              | Default                 | What it is                                   |
| --------------------- | ----------------------- | -------------------------------------------- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base URL of the backend API (see `backend/`) |

Read it only through [`lib/api/client.ts`](lib/api/client.ts) (`API_URL`, `apiUrl("/health")`, `apiFetch`). The dashboard shows whether the API is reachable; with the backend running (`cd backend && uv run fastapi dev`), it says "API online". Next.js copies `NEXT_PUBLIC_` values into the JavaScript sent to browsers when the app is built, so:

- never put a secret in one;
- restart `npm run dev` after changing one;
- in Vercel, set it per environment (Production, Preview), because the value is frozen into each deployment when it's built.

## Scripts

| Command         | What it does                                          |
| --------------- | ----------------------------------------------------- |
| `npm run dev`   | Start the dev server on port 3000                     |
| `npm run build` | Production build (also type-checks the project)       |
| `npm run start` | Serve the production build (run `build` first)        |
| `npm run lint`  | Lint with ESLint                                      |

## Project structure

```
app/                      # Routing only: layouts, pages, loading/error/not-found
├── layout.tsx            # Root layout: <html>, fonts (Geist), theme script, title template
├── globals.css           # Tailwind, design tokens (light and dark), global utilities
├── not-found.tsx         # 404 page
├── (app)/                # Pages inside the app shell (URLs don't include "(app)")
│   ├── layout.tsx        # Sidebar, header, footer
│   ├── loading.tsx       # Shared loading skeleton
│   ├── error.tsx         # Shared error boundary
│   ├── page.tsx          # Dashboard (/)
│   └── time-machine/, backtests/, backtests/new/, revisions/, filings/,
│       experiments/, methodology/, privacy/, assistant/, compare/
└── (auth)/               # Sign-in and sign-up, without the app shell
components/
├── ui/                   # shadcn/ui primitives (generated, then owned by us)
├── layout/               # App shell: sidebar, header, footer, page header, theme toggle
└── feedback/             # Shared states: planned page, error state
features/                 # One folder per feature: its components, data, actions
├── dashboard/
├── time-machine/
├── backtests/
└── auth/
config/
├── site.ts               # Name, links, required notices
└── navigation.ts         # Every route: title, icon, status, roadmap story
hooks/                    # Shared React hooks
lib/
├── api/                  # Backend client: client.ts (API_URL, apiFetch), one file per endpoint group
├── time.ts               # Market-time (ET) parsing and formatting
├── theme.ts              # Light and dark theme helpers
└── utils.ts              # cn() for merging class names
components.json           # shadcn/ui CLI settings
GUIDELINES.md             # Design system, conventions, and project rules
```

Most pages are placeholders for now: each shows what it will do and which roadmap story and milestone deliver it. All of that comes from [`config/navigation.ts`](config/navigation.ts).

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
