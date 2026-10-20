# Frontend guidelines

How we build the Quant Time Machine web app: the design system, where code goes, and the rules every page follows. Read it before your first frontend pull request; reviewers check against it.

## Rules at a glance

1. **Style with tokens.** Use the semantic Tailwind classes (`bg-card`, `text-muted-foreground`, `text-future`, `bg-known/10`). Never raw palette classes (`bg-blue-500`), hex values, or `dark:` color overrides.
2. **Show time honestly.** Market times are New York time, labelled ET, and formatted only with `lib/time.ts`. Anything not yet public at the knowledge time looks different from what was (see [the knowledge horizon](#2-the-knowledge-horizon)).
3. **Reuse before you build.** Use `components/ui` (shadcn/ui) and the shared components below. Add missing primitives with the shadcn CLI, not by hand-rolling them.
4. **Server Components by default.** Add `"use client"` only to the small leaf components that need state, effects, or browser APIs.
5. **Every backend call goes through `lib/api/`.** No `fetch` to the API from pages or components.
6. **Every route is registered once in `config/navigation.ts`.** The sidebar, page titles, and placeholders read from it.
7. **Accessible by default.** Labels on every input, visible focus, keyboard support, AA contrast, and color is never the only signal.
8. **Plain words, no advice.** Use the glossary terms; never phrase anything as an investment recommendation.
9. **Check the states.** Loading, empty, and error states exist; pages work at 375 px, 768 px, and desktop widths, in light and dark.
10. **CI must pass.** `npm run lint && npm run build`, plus a screenshot in the pull request for UI changes.

## 1. Principles

- **Honest by construction.** The product exists to prevent look-ahead bias, so the interface never blurs what was known at a moment with what came later.
- **Show the evidence.** Assumptions (decision time, fill rule, costs, data version), timestamps, and sources are visible, not buried (NFR-3).
- **One system.** Pages are assembled from shared components and tokens. If a page needs a one-off style, the design system is missing something: add it there.
- **Calm and dense.** This is a research tool: compact `text-sm` body text, borders instead of heavy shadows, color reserved for meaning.

## 2. The knowledge horizon

Our core visual idea. A vertical line marks the knowledge time *T*:

| | Known at *T* | Not yet known at *T* |
| --- | --- | --- |
| Meaning | Public at or before *T* (`available_at ≤ T`) | Public only after *T* |
| Color | `known` (brand indigo-blue) | `future` (amber) |
| Shape | Solid borders, filled dots | Dashed borders, hollow dots, `bg-hatch-future` "fog" |
| Badge | `<Badge variant="known">` | `<Badge variant="future">` |
| Words | "Known", "public at or before T" | "Not yet known", "public after T" |

Always pair the color with a shape, icon, or label, so the meaning survives color blindness and grayscale printing. `features/time-machine/knowledge-horizon.tsx` is the reference implementation; the Time Machine, the audit drill-down, and the bias reports should all reuse this language.

## 3. Design tokens

Tokens are CSS variables in `app/globals.css`, defined for light (`:root`) and dark (`.dark`) and mapped to Tailwind colors. The names match shadcn/ui, so components added with the CLI pick up our theme.

| Token | Use it for |
| --- | --- |
| `background` / `foreground` | The page and its body text |
| `card` / `card-foreground` | Cards, panels, list items on a card |
| `popover` | Menus, popovers, sheets |
| `muted` / `muted-foreground` | Subtle fills; secondary text (descriptions, captions, labels) |
| `primary` / `primary-foreground` | The main action on a page, links, the active nav item, the brand mark |
| `secondary`, `accent` | Low-emphasis buttons; hover and selected states in menus |
| `border`, `input`, `ring` | Dividers and outlines; form control borders; focus rings |
| `destructive` | Errors and destructive actions |
| `known` | Facts public at the knowledge time |
| `future` | Facts not yet public at the knowledge time; also cautions and warnings |
| `positive` / `negative` | Gains and losses, healthy and unhealthy status |
| `chart-1` … `chart-5` | Chart series: `chart-1` for the strategy, `chart-2` (gray) for the benchmark |
| `sidebar-*` | The app sidebar only |

- Opacity modifiers are fine and expected: `bg-known/10`, `border-future/40`.
- Every text pair meets WCAG AA (4.5:1) in both themes, including colored text on its own 10% tint. If you add or change a token, set it in both themes and check the contrast.
- Dark mode is a `.dark` class on `<html>`, so `dark:` variants work, but prefer tokens that already switch.

## 4. Typography, spacing, and layout

- **Fonts.** Geist Sans for the interface. Geist Mono with `tabular-nums` for timestamps, tickers, IDs, numbers in tables, and code (`font-mono tabular-nums`).
- **Scale.** One `h1` per page, via `PageHeader` (`text-2xl font-semibold`). Section headings are `text-base font-semibold`; card titles use `CardTitle`. Body text is `text-sm`; captions and metadata are `text-xs text-muted-foreground`.
- **Page anatomy.** `PageHeader` (title, subtitle, badge, actions), then sections, usually `Card`s, stacked with `gap-6`. The app shell already provides the `max-w-6xl` container and padding; don't add another.
- **Responsive.** Build mobile first. The sidebar becomes a sheet below 768 px (`md`). Use `md:` and `lg:` grid columns for side-by-side content. Check 375, 768, and 1280 px wide.
- **Motion.** Keep it functional (opening sheets, tooltips). `prefers-reduced-motion` is respected globally.

## 5. Components

### shadcn/ui

Primitives live in `components/ui/` and come from [shadcn/ui](https://ui.shadcn.com) on [Radix UI](https://www.radix-ui.com) (style `radix-nova`, see `components.json`). The code is ours: it's copied into the repository, not imported from a package.

- **Add a component:** from `frontend/`, run `npx shadcn@latest add <name>`, for example `select`, `tabs`, `table`, `dialog`, `popover`, `calendar`. Review the generated file, run lint, and say in the pull request that it's generated.
- **Customize** through tokens and `cva` variants (see `badge.tsx` and `alert.tsx`), not by restyling a component on one page.
- **Edits to generated files** are deliberate and minimal, with a comment explaining why. So far: project variants in `badge.tsx` and `alert.tsx`, and `hooks/use-mobile.ts` rewritten with `useSyncExternalStore` to pass the React hooks lint rules. Re-running `add --overwrite` would undo them.
- `cn()` merges class names (the `cn` package, shadcn's replacement for `clsx` + `tailwind-merge`). Import it from `@/lib/utils` in our code.

| Component | Use it for |
| --- | --- |
| `Button` | Actions. `default` for the main action, `outline` or `ghost` for the rest. Style a `Link` as a button with `<Button asChild>`. |
| `Card` | Grouped content: `CardHeader`, `CardTitle`, `CardDescription`, `CardAction`, `CardContent`, `CardFooter`. `size="sm"` for compact cards. |
| `Badge` | Short status labels. Variants: `known`, `future`, `positive`, `negative`, `outline`, `secondary`, `destructive`. |
| `Alert` | Inline notices. `info` for neutral explanations, `warning` for cautions, `destructive` for errors. |
| `Field`, `Input`, `Label` | Every form control: `Field`, `FieldLabel`, the control, `FieldDescription`, `FieldError`. |
| `Empty` | Empty states, always with a next action. |
| `Skeleton`, `Spinner` | Loading placeholders shaped like the content; pending buttons. |
| `Tooltip` | Supplementary labels only (for example, icon-only buttons). Never the only place information lives. |
| `Sheet`, `Separator`, `Sidebar` | Used by the app shell. |

### Project components

| Component | Where | What it does |
| --- | --- | --- |
| `PageHeader` | `components/layout/` | The top of every page: `h1`, subtitle, badge, actions |
| `PlannedPage` | `components/feedback/` | Placeholder for an unbuilt page, from its `config/navigation.ts` entry |
| `ErrorState` | `components/feedback/` | Failure message with retry; used by `error.tsx` |
| `ThemeToggle`, `Brand`, `AccountNav` | `components/layout/` | Shell pieces |
| `KnowledgeHorizon` | `features/time-machine/` | Known vs. not-yet-known split at a moment |
| `SpecSummary` | `features/backtests/` | An experiment spec in plain language, with its JSON |

**Icons:** [Lucide](https://lucide.dev) via `lucide-react`, using the `…Icon` names (`CalendarClockIcon`). Default size is `size-4`; decorative icons get `aria-hidden`. Lucide 1.x has no brand logos.

## 6. States

Every view that loads data designs all of these:

- **Loading.** A route-level `loading.tsx`, or `<Suspense>` around the slow part, showing `Skeleton`s shaped like the content.
- **Empty.** `Empty` with a title, one sentence on why it's empty, and the next action.
- **Error.** `error.tsx` boundaries render `ErrorState` with `retry`. Say what failed and what to do; never show a stack trace.
- **Planned.** Pages that don't exist yet render `PlannedPage`, which shows the story and milestone from the roadmap.
- **Validation.** Errors appear next to their field via `FieldError`, with `aria-invalid` and `aria-describedby` on the control. The server is the source of truth: the API's 422 field paths (S9.5) map onto fields.

## 7. Accessibility

Target WCAG 2.2 AA; NFR-12 asks for keyboard-usable forms, sufficient contrast, and a layout that works at tablet width.

- Use semantic HTML first: one `h1`, ordered headings, landmarks (`header`, `nav`, `main`, `footer`), lists for lists, `<button>` for actions and `<a>`/`Link` for navigation.
- Every input has a visible label. Icon-only buttons have an `aria-label` or `sr-only` text.
- Focus is always visible (the token `ring`), and everything works with the keyboard. The shell has a skip link to `#main-content`.
- The current page's nav link has `aria-current="page"`.
- Status changes that aren't navigation (form results, run progress) go in a `role="status"` region.
- Never rely on color alone (see [the knowledge horizon](#2-the-knowledge-horizon)); signed numbers keep their `+`/`−` sign.

## 8. Time, numbers, and words

- **Time.** The market clock is `America/New_York`. Show market times as ET with the label ("June 5, 2020, 9:30 AM ET"), using `lib/time.ts`. Never use `toLocaleString()` or the viewer's time zone: results differ between server and browser and break hydration. A bare date means 09:30 ET on that date (roadmap §2.2).
- **Provenance.** Wherever a value appears, its `available_at` and source should be one step away.
- **Numbers.** `tabular-nums`, consistent precision within a column, units in the header (%, bps, $). Returns use `positive`/`negative` plus the sign.
- **Words.** Use the glossary (doc/roadmap.md §11): knowledge time, as of, `available_at`, known, not yet known, decision, fill, vintage, data version. Sentence case for headings and buttons. Say exactly what happened ("You're not signed in: accounts aren't live yet"), not "Oops!". Never recommend trades or imply predictions; the footer carries the disclaimer and FRED's notice.

## 9. Code conventions

### Where code goes

```
app/            Routing only: layouts, pages, loading/error/not-found. No reusable UI.
  (app)/        Pages inside the app shell (sidebar, header, footer)
  (auth)/       Sign-in and sign-up, without the shell
components/
  ui/           shadcn/ui primitives
  layout/       The shell: sidebar, header, footer, page header, theme
  feedback/     Shared states: planned page, error state
features/<name>/ Code for one feature: its components, presets, types, actions
config/         Site constants and the route registry
hooks/          Shared React hooks
lib/            Framework-agnostic helpers: api/, time, theme, utils
```

- Start feature code in `features/<name>/`. Move it to `components/` or `lib/` once a second feature needs it.
- Features don't import each other, except `features/dashboard`, which composes the others.

### Files and components

- File names are kebab-case (`page-header.tsx`); components are PascalCase named exports. Default exports only for Next.js special files (`page`, `layout`, `loading`, `error`, `not-found`).
- One main component per file; small private helpers can sit below it.
- Props are a `type` above the component. No `any`.
- Import across folders with `@/`; relative imports only within the same folder.
- No formatter is configured yet: match the surrounding file. Our files use double quotes and semicolons; generated shadcn files keep their own style.

### Server and client

- Components are Server Components unless they need state, effects, event handlers, or browser APIs. Keep `"use client"` components small and at the leaves.
- Don't pass functions, including Lucide icons, from a Server Component to a Client Component; import them inside the Client Component instead.
- Server Actions: `"use server"` files may only export async functions. Put types, constants, and validation in a plain module next to them (see `features/auth/`).

### Data and URL state

- Call the backend only through `lib/api/` (`apiFetch` plus one typed function per endpoint). The backend accepts browser (CORS) requests only from the origins in its `CORS_ORIGINS` setting (S8.1), which defaults to `http://localhost:3000`. Before fetching from the browser on a deployed site, add that site's origin there.
- Hand-written API types are temporary; generate them from the OpenAPI schema when S8.6 lands.
- Shareable state lives in the URL, using the API's parameter names: `as_of`, `tickers`, `series`, `preset`. Parse and validate on read (see `parseAsOf`).

### Styling

- Tailwind utilities with tokens, merged with `cn()`. Variants with `cva`. No CSS modules, and inline `style` only for dynamic CSS variables.
- New global CSS (utilities, keyframes) goes in `app/globals.css` with a comment.

### Dependencies

Every new dependency is justified in its pull request: what it does that our stack doesn't. Prefer the platform and what's already installed.

## 10. Next.js 16 notes

This version differs from older tutorials and training data. Before using an API, read its page in `node_modules/next/dist/docs/` (see `AGENTS.md`). Things that matter here:

- `params` and `searchParams` are Promises. Type pages with the generated helpers: `async function Page(props: PageProps<"/time-machine">)`, then `await props.searchParams`.
- `typedRoutes` is on: `Link` `href`s and router calls are type-checked, so a link to a missing page fails the build. Cast a computed string with `as Route` only when you must.
- `error.tsx` receives `retry` (preferred over `reset`).
- Route protection (S16.3) belongs in `proxy.ts`; `middleware.ts` is deprecated.
- `next/form` gives GET forms client-side navigation (see the dashboard's quick start).
- In development, React Strict Mode remounts the page and resets attributes on `<html>`; `ThemeSync` re-applies the theme class.
- `cacheComponents` is off. Mark request-time data with `await connection()` (see `ApiStatus`).

## 11. Adding a page

1. Add an entry to `routes` in `config/navigation.ts` (title, `href`, icon, description, status, roadmap story, highlights). If it belongs in the sidebar, add it to `navSections`.
2. Create `app/(app)/<path>/page.tsx`: export `metadata = routeMetadata(routes.<name>)` and render `PlannedPage` until the real UI exists.
3. Build the UI in `features/<name>/`, composed from `components/ui` and the shared components.
4. Design the loading, empty, and error states; check 375 px, 768 px, and desktop, in light and dark.
5. Run `npm run lint && npm run build`, and attach a screenshot to the pull request (Definition of Done).
