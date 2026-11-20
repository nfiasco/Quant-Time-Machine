# Supabase accounts

Supabase Auth owns accounts; the point-in-time market-data store stays in Parquet/DuckDB. This directory contains the CLI configuration, reviewed SQL migrations, and an intentionally empty seed. Saved experiments and their RLS policies are separate work in S16.2/S16.5; signing in does not yet save research.

## Hosted development setup record

Checked 2026-11-16 for S16.1 (#186):

| Item | Evidence / status |
| --- | --- |
| Existing project | Local CLI link identifies project `fjuwinoxwmjddotdpghj`, named `Quant-Time-Machine` |
| Project URL | `https://fjuwinoxwmjddotdpghj.supabase.co` |
| Auth health | Authenticated `/auth/v1/health` returned HTTP 200 using the public key. |
| Project status / region | Authenticated `supabase projects list`: `ACTIVE_HEALTHY`, `us-west-2`, PostgreSQL 17 |
| Plan | Free-plan membership not verified; confirm in the dashboard |
| Team access | This machine's CLI session can list the project, read API keys, and connect to its database. Other teammates' access still needs confirmation before #186 is complete. |
| Auth environment | The public key was retrieved through the CLI and saved only in ignored `frontend/.env.local`; no secret/service-role key was saved. This checkout runs at `http://localhost:3001`. |
| Hosted Auth | Public `/auth/v1/settings` confirms email enabled, sign-up allowed, email confirmation required; JWKS publishes ES256. Synthetic invalid-credential sign-in was verified through the web form. |
| Migration history | `migration list` connected successfully; `db push --dry-run` reports only `20261116000000_auth_foundation.sql` pending. Nothing was applied. |
| SMTP, redirect allow-list, password policy | Not verified/changed; add the checkout's exact callback (`http://localhost:3001/auth/callback`) before testing email flows. |

Do not create a duplicate project. This worktree is now linked; new clones/worktrees must link separately because `.temp/project-ref` is ignored. A maintainer should confirm Free-plan membership and each teammate's access, record the results here, and use:

```sh
npx supabase login
npx supabase projects list
npx supabase link --project-ref fjuwinoxwmjddotdpghj
npx supabase migration list
npx supabase db push --dry-run
# After the migration PR is reviewed, apply it with: npx supabase db push
```

Before applying to an existing hosted database, compare migration history and review any old sample-data tables. The initial migration changes defaults for future tables/functions; it neither imports market data nor changes existing table grants. Existing sample-data tables need a separate access review before using the project for private user data.

## Local CLI and Docker

Install Node.js 24 (the repository's `.nvmrc`) and a running Docker-compatible engine. Run CLI commands from the repository root:

```sh
npx supabase --version
npx supabase start
npx supabase status
# Local only: erase/recreate the local database, replay migrations, then seed.
npx supabase db reset --local
```

`status` prints local credentials: copy its API URL and **publishable/anon** key into an ignored `frontend/.env.local`, using `frontend/.env.example` as the template. Never copy its secret/service-role key into the frontend. Set `SITE_URL=http://localhost:3000` and open that hostname consistently: PKCE cookies belong to the browser and hostname where the email was requested. The local email inbox is at `http://127.0.0.1:54324`; Studio is at `http://127.0.0.1:54323`.

```sh
cd frontend
npm ci
npm run dev
```

Local email confirmations are enabled, and passwords require at least 8 characters. Use the local inbox to confirm an account and follow recovery links without sending real emails. Stop services with `npx supabase stop`; do not use `--no-backup` unless you intend to discard local data. Docker was not available during this implementation, so local migration replay remains to be verified on a Docker-equipped machine.

## Migration workflow

1. Start local Supabase, then create `npx supabase migration new descriptive_name`.
2. Write SQL in the timestamped file under `migrations/`. Do not edit an already-applied migration; add another migration to correct it.
3. Run `npx supabase db reset --local` to prove a fresh database can replay the whole history and find `seed.sql`.
4. Review SQL in a PR. New private tables require RLS, explicit grants, owner checks using `auth.uid()`, and cross-user tests (S16.2). Default privileges are deliberately restricted by the first migration.
5. After review, inspect `migration list` and `db push --dry-run` for the linked development project before applying `db push`. Never run a linked/remote reset as part of ordinary development.

Use SQL migrations for schema, not dashboard table edits. Auth provider, email, and redirect settings are configured separately in the hosted dashboard; `config.toml` describes local services, and `db push` does not synchronize hosted Auth settings.

## D9: authentication and token verification

Decision recorded 2026-11-16, pending team review: **Supabase email/password accounts, email confirmation, and password reset emails**. GitHub OAuth/magic-link sign-in can be added later. The web app uses the official `@supabase/supabase-js` and `@supabase/ssr` packages, which provide Auth API calls, PKCE, cookie storage, and refresh behavior that Next.js does not supply itself.

Server Actions validate inputs and invoke Auth; credentials are never stored by this application. Auth tokens persist in HttpOnly, SameSite=Lax cookies (Secure in production). There is no browser Supabase client, and no service-role key is used. Next.js Proxy refreshes and verifies sessions with `auth.getUser()` and preserves refreshed cookies through redirects. The header and private page repeat verification on the server. `getSession()` or a decoded cookie is never an authorization decision. Personalized responses and auth redirects use `Cache-Control: private, no-store`. A failed provider request cannot admit a user to a private page.

`/experiments` and its descendants need an account; the registry's `requiresAccount` flag is the source of truth. `/reset-password` also requires a verified session. The landing page, dashboard, market-data views, and canonical backtest remain public. Sign-in returns users to a validated internal destination. Sign-out revokes the current session and clears its cookies; other devices stay signed in.

**Backend verification implemented for S16.4 (#188):** the reusable FastAPI `CurrentUser` dependency verifies each private request against the configured project's public JWKS. PyJWT with `cryptography` validates ES256/RS256 signatures, issuer `${SUPABASE_URL}/auth/v1`, audience `authenticated`, expiry, required claims, the authenticated role, and a UUID user subject. Anonymous users, public/service-role keys, unsigned tokens, wrong-project tokens, and malformed/expired credentials cannot authorize a request. Token header URLs never select a key source. Verification runs in a worker thread, with 5-second network timeouts.

Only the JWKS is cached (default 300 seconds, configurable 30–600). Individual keys and user identities are not cached indefinitely. Unknown key IDs can trigger a key-set refresh at most once every 30 seconds, allowing rotation without a request flood; a new key may wait for that cooldown. Asymmetric access tokens are verified locally and remain valid until their expiry even after refresh-session sign-out; the frontend deletes its session cookies on sign-out.

`GET /v1/me` requires `Authorization: Bearer <access-token>` and returns only `{"user_id":"<verified UUID>"}`. Missing/invalid tokens get 401 with a Bearer challenge; missing server configuration or unavailable key verification gets a generic 503. Responses are `private, no-store` and excluded from the market-data response cache, even if `as_of` is supplied. Health, market-data/catalog routes, and the current public backtest/run routes remain public; those runs are not private saved experiments. Future private handlers must declare `user: CurrentUser` and use that verified ID for owner checks.

The Experiments page now forwards its HttpOnly session's opaque access token through a server-only `lib/api/account.ts` call to `/v1/me`, verifies the returned subject matches its already-verified Supabase account, and shows a retryable error if the API cannot verify it. Tokens never appear in page props, URLs, or response bodies. Saved experiments and RLS isolation remain S16.2/S16.5.

For legacy/local HS256 projects only, set `SUPABASE_ALLOW_LEGACY_HS256=true` plus the public `SUPABASE_PUBLISHABLE_KEY`. The backend checks registered claims and then requires the fixed project's Auth `/user` endpoint to verify the signature and return the same subject. This fallback is off by default. No shared JWT signing secret or service-role key is used. See the [Supabase JWT guide](https://supabase.com/docs/guides/auth/jwts) and [PyJWT API](https://pyjwt.readthedocs.io/en/stable/api.html).

### Run this worktree

The ignored environment files in this worktree already point both apps at the existing hosted project. In two terminals:

```sh
cd /home/ian-guy/Quant-Time-Machine/.worktrees/supabase-auth/backend
uv sync --locked
uv run fastapi dev
```

```sh
cd /home/ian-guy/Quant-Time-Machine/.worktrees/supabase-auth/frontend
npm ci
npm run dev -- --webpack --port 3001
```

Open `http://localhost:3001/sign-in`. Supabase's hosted redirect allow-list must include `http://localhost:3001/auth/callback` before testing emails. `http://localhost:8000/v1/me` returns 401 without a token; `/health` remains public. On Railway, set `SUPABASE_URL` to the same project as the frontend; the hosted ES256 project needs no backend API key. Do not overwrite an existing `.env` file when configuring a different checkout.


## Hosted Auth configuration

For each environment (including individual Vercel previews):

- Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` to the same project. The legacy public anon key also works. Secret/service-role keys are rejected by the app.
- Set server-only `SITE_URL` to the exact frontend origin. Add `${SITE_URL}/auth/callback` to Supabase Auth's redirect allow-list, and set its Site URL. Avoid broad production wildcards.
- Enable email/password sign-up, **Confirm email**, and minimum password length 8 in the hosted dashboard. SQL migrations do not change these settings.
- Standard Supabase `{{ .ConfirmationURL }}` email templates work with the PKCE `/auth/callback?code=...` handler. Open links in the same browser used to request them. Invalid/expired links offer a new request rather than showing raw provider errors.
- Optional cross-browser token-hash templates are supported at `/auth/confirm`: confirmation uses `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=signup`; recovery uses `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery`. The handler accepts only those two token types and sends recovery sessions to `/reset-password`.
- Configure a real SMTP provider for hosted teammate/demo mail. Supabase's built-in mail service restricts recipients and delivery rates; validate sender delivery before the demo. Do not add SMTP credentials to source control.

Blank/invalid environment settings produce an explicit unavailable state and disabled forms. Production confirmation/recovery requests also require `SITE_URL`. The examples contain placeholders only. Keep actual settings in ignored `.env` files or hosting secrets; restarting/rebuilding is required after changing public frontend variables.

## Validation and demo-day checklist

`cd frontend && npm run lint && npm test && npm run build` checks the app. `features/auth/auth-flow.test.ts` exercises the real Supabase SSR SDK against a synthetic Auth API: sign-in, fresh-client cookie persistence, route protection, sign-out, invalid credentials, missing configuration, confirmation, recovery, password update, and invalid email links. It needs no hosted credentials and does not send mail. The production build can also use `npm run build -- --webpack` where Turbopack's internal process/port binding is restricted.

Before marking #186/#187 complete, verify with local/hosted Auth:

- Confirm project health, Free plan, team access, migration history, and local migration replay; update the setup record above.
- Register a disposable test address, confirm its email, sign in, reload, and verify the header stays signed in.
- Visit `/experiments` signed out, sign in, and check the return destination; verify public research still works signed out.
- Request a reset, follow the email, change the password, then sign out and sign in with the new password. Check expired links and a wrong password.
- Check keyboard operation, error announcements, 375/768/1280 px widths, both themes, and 200% zoom. Automated tests do not establish screen-reader conformance.

Supabase Free includes **500 MB database storage per project**, **two active free projects**, and projects can be **paused after one week of inactivity** (checked 2026-11-16; see [pricing](https://supabase.com/pricing) and [billing FAQ](https://supabase.com/docs/guides/platform/billing-faq)). Keep market data out of this database. A day before a demo, open the dashboard, restore the development project if paused, wait for healthy services, confirm migrations, and rehearse confirmation/sign-in/reload/reset/sign-out. Repeat a quick sign-in before presenting. Keep local Docker Supabase and its email inbox available as a fallback. An uptime guarantee would require a plan decision; periodic traffic is not a guarantee against pausing.

References: [Supabase Next.js SSR](https://supabase.com/docs/guides/auth/server-side/nextjs), [password-based Auth](https://supabase.com/docs/guides/auth/passwords), [JWT verification](https://supabase.com/docs/guides/auth/jwts), [local development](https://supabase.com/docs/guides/local-development).

### Implementation check results (2026-11-16)

- Frontend lint passed; 111 tests passed, including the SDK-backed auth flow, PKCE recovery exchange, cookie refresh, and external-redirect rejection.
- `npm run build -- --webpack` passed with hosted public settings. The default Turbopack builder hit this environment's internal port-binding restriction.
- Backend Ruff lint/format passed; 1,063 fixture tests passed (71 opt-in network/local-data tests deselected). All 14 settings tests passed independently as well.
- All 13 repository organization-policy tests passed.
- Browser checks covered 375, 768, and 1280 px layouts, light/dark themes, account-page redirect preservation, configured sign-in/sign-up/recovery forms, and a live synthetic invalid-credential response. Successful account creation, confirmation mail, password-reset mail, screen-reader behavior, and 200% zoom have not been verified.
- Auth health, email provider/confirmation flags, ES256 JWKS, and hosted migration dry run succeeded. Local CLI status parsed the configuration but could not inspect services because neither Docker nor Podman is installed.
- `npm audit` found no Supabase-package advisories. The frontend toolchain has 17 existing advisories, including a high-severity `body-parser` advisory; unrelated dependency updates remain separate work.


### FastAPI integration checks (2026-11-19)

Current main was merged into the auth branch. Backend Ruff lint/format and all 1,298 fixture tests passed (71 opt-in network/local-data tests deselected), including 47 auth-boundary tests with generated ES256/RS256 keys. Frontend generated API-type checks, lint, Prettier, and all 125 tests passed, as did the Next.js 16.4.6 Webpack production build. The 13 repository organization-policy tests passed.

Live local HTTP checks confirmed `/v1/me` returns 401 with a Bearer challenge and `private, no-store` without a token; `/health` and `/v1/catalog/signals` returned 200. Both ignored environment files are configured for the same hosted project. The new caller identity is never stored in the public as-of cache.

Fresh browser inspection was blocked by browser policy, so the PR uses the previously captured sign-in screenshot in `doc/images/auth-sign-in-2026-11-16.png` and labels its capture date. Successful real-email signup/recovery, SMTP/redirect configuration, Free-plan/other-team-member access, local Docker migration replay, and private experiment/RLS storage remain the documented follow-up scope. The hosted foundation migration has not been applied.
