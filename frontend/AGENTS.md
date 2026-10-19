<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Project rules

Written by the team; `next dev` doesn't touch anything outside the markers above.

Follow [`GUIDELINES.md`](GUIDELINES.md) for every frontend change. The rules most often missed:

- Style with the design tokens (`bg-card`, `text-muted-foreground`, `text-future`, `bg-known/10`), never raw Tailwind palette colors or hex values.
- Use the components in `components/ui/` (shadcn/ui). Add missing ones with `npx shadcn@latest add <name>`; don't hand-roll primitives.
- Register every route in `config/navigation.ts`; pages take their metadata from it with `routeMetadata`.
- Call the backend only through `lib/api/`. Format market times only with `lib/time.ts` (New York time, labelled ET).
- Server Components by default; `"use client"` only on small leaf components.
- Run `npm run lint && npm run build` before calling a change done.
