# Backend and data hosting (decision D4)

> **Spike S1.6.** Decided 2026-10-23, pending team review. The measurements come from [`backend/spikes/hosting.py`](../backend/spikes/hosting.py), run on the real M2 store (ingested 2026-10-23) on a laptop and on the deployed machine. Prices and limits were checked on 2026-10-23. They change, so check them again before S15.1. Updated 2026-10-29: the team deferred the card until a host is needed, before S8.4 (Sprint 4). The free trial lapsed on 2026-10-31, and Sprint 3 runs locally. Also re-evaluated on 2026-10-29, with one owner allowed and AWS Lambda and Cloudflare added ([re-evaluation](#re-evaluation-2026-10-29-one-owner-aws-lambda-and-cloudflare)). Updated 2026-10-31: with a $5-a-month limit and the owner willing to do the setup, AWS Lambda is the lead candidate. A spike before S8.4 decides, with Fly as the fallback ([plan](#plan-2026-10-31-try-aws-lambda-first-with-fly-as-the-fallback)).

## Decision

**The API runs on Fly.io.** It's a container built from [`backend/Dockerfile`](../backend/Dockerfile), on one shared-CPU machine in Ashburn, Virginia (`iad`), with the point-in-time store on a 1 GB volume at `/data`. The configuration is [`backend/fly.toml`](../backend/fly.toml).

- **Deployed** at <https://quant-time-machine-api.fly.dev> on Fly's free trial, which lapsed on 2026-10-31, so the URL no longer answers. The card is deferred until a host is needed again, before S8.4 ([Cost and the trial](#cost-and-the-trial)).
- **Next:** AWS Lambda is the lead candidate for that host, and a spike before S8.4 decides between it and Fly ([plan](#plan-2026-10-31-try-aws-lambda-first-with-fly-as-the-fallback)).
- **Why Fly:**
  - **A disk for the store,** which changes only when we ingest. Vercel has no disk, and Render's free tier has none.
  - **A long-lived process,** which backtests need (S8.4). Vercel caps a request at 300 seconds on Hobby, and background work there needs extra services.
  - **No seat fees for the five of us.** Vercel's team features cost $20 per developer seat. Render's free workspace allows one member, and its Pro plan is $25 a month. Railway's Hobby plan is for one developer.
  - **The cheapest always-available option with a disk:** at most about $4 a month, and less with auto-stop.
  - **A container,** so production runs our exact Python 3.14 and `uv.lock`. `fly deploy` builds on Fly's servers, so nobody needs Docker installed.
- **What we accept:**
  - Fly needs a card. The team deferred adding one until a host is needed, before S8.4.
  - Deploys run from the command line until S15.1 adds a GitHub Action.
  - A volume belongs to one machine and isn't replicated. The store can be rebuilt by ingesting again, and Fly snapshots the volume daily.
  - Shared CPUs are throttled under sustained load, which shapes how backtests run (below).

## What we measured

### Data size

The real M2 store: six series, six companies' filings, and six tickers' prices since 2005.

| Table | Rows | Files | Bytes |
| --- | ---: | ---: | ---: |
| `macro_observations` | 24,552 | 6 | 176,571 |
| `securities` | 19 | 1 | 3,399 |
| `sec_tickers` | 10,425 | 1 | 141,713 |
| `price_bars` | 27,837 | 6 | 717,659 |
| `corporate_actions` | 333 | 5 | 14,116 |
| `filings` | 2,663 | 5 | 98,254 |
| **Total** | **65,829** | **24** | **1,151,712** |

- **Parquet is compact:** about 17.5 bytes per row, provenance columns included.
- **The raw cache isn't deployed.** It held 42 MB: FRED 2.4 MB in 18 responses, SEC 32.5 MB in 84 (mostly JPMorgan's 72 history pages), and Tiingo 7.1 MB in 6. It stays on the machine that ingests.
- **For the ~100-security starter universe (D3)** the store stays far below the 1 GB volume. `fly volumes extend` can grow it later without moving data.
  - **Prices:** 5,487 sessions since 2005 for a stock listed throughout, so about 550,000 rows, or 14 MB at the measured 26 bytes per row.
  - **Filings:** about 440 per company on average, so about 44,000 rows, under 2 MB.
  - **XBRL facts (S5.5)** are the unknown. At 20,000–50,000 facts per company, 100 companies make 2–5 million rows, or roughly 50–150 MB.

### The image and requests

- **The image** is 191 MB. Its installed packages take 279 MB, with compiled bytecode; on a Mac they take 172 MB. That fits under Vercel's 500 MB limit for Python functions, but leaves little room for the data and for growth.
- **A warm request** for a macro value, a filing, or an error takes 0.05–0.12 seconds end to end from a laptop.
- **A cold start** takes 7.2 seconds: the first request after auto-stop stopped the machine waits for it to boot and import the app.

### A backtest-shaped workload

The spike opens one `PointInTimeView` per month's first trading day from 2010 to 2025 at 09:30 ET, 192 decisions in all. Each decision reads UNRATE plus, for each of N tickers, a 252-session price history and the latest 10-Q, the reads the canonical example's signals make. The six M2 tickers take turns standing in for a universe of N.

| | Apple-silicon Mac | Fly `shared-cpu-1x`, bursting | Fly `shared-cpu-1x`, throttled |
| --- | --- | --- | --- |
| Per read | 3.8 ms | 10.6 ms | 110 ms |
| Opening a view | 7.5 ms | 14.7 ms | 132 ms |
| 100 tickers (38,592 reads) | 150 s, measured | About 7 minutes | About 70 minutes |
| Peak memory | 303 MB | 162 MB | 158 MB |

- **Mac:** measured with 100 tickers, using about 3.2 cores, since DuckDB runs in parallel.
- **Fly, bursting:** measured with 10 tickers, just after the deploy.
- **Fly, throttled:** measured with 2 tickers, on a machine that had just woken up.
- **The full 100-ticker run couldn't finish on Fly,** because the trial stopped a machine after 5 minutes, so its times are extrapolated per read. Once a card is added it can run in full. Do that once the universe (S6.5) is loaded, so S8.4 has measured numbers.

**Why the throttled column exists.** A `shared-cpu-1x` machine is guaranteed 6.25% of a CPU (5 ms of every 80 ms). It runs at full speed only while it has a burst balance. The balance grows from unused time while the machine idles, up to 500 seconds, but a machine that just started, as auto-stop machines do on every wake, begins with 5 seconds of it ([Fly CPU performance](https://docs.fly.io/machines/cpu-performance)). Throttled, the same reads ran about 10 times slower.

## How long backtests would run there

Lookups are fine as ordinary requests, even after a cold start. A canonical-size backtest done with one query per ticker per decision takes minutes at full speed and over an hour throttled. So:

1. **S8.4 runs backtests in the background,** and the page polls for status. One request can't hold a run that long: nobody waits for it, and Fly's proxy reportedly drops a connection that sends nothing for 60 seconds ([forum answer](https://community.fly.io/t/request-timeouts-on-fly-io/5653)).
2. **The engine batches its reads (S7.3, S15.2).** Per-ticker reads make about 200 queries per decision. One query per decision, or one `ASOF JOIN` for the whole run as [`storage.md`](storage.md) benchmarked, cuts the work by orders of magnitude.
3. **The API stays on a shared CPU, which is plenty for lookups.** For backtests, either:
   - start a `performance-1x` machine (a dedicated CPU, 2 GB) for each job. It's $33 a month if always on, billed by the second, so a 10-minute run costs under a cent.
   - or keep one shared machine running, so it builds up to about 8 minutes of full-speed burst.

   Decide in S8.4, with the real engine's timings.
4. **A machine must stay up during a run.** Auto-stop stops a machine that gets no HTTP traffic, even mid-job. A page that polls keeps it up, but a closed page wouldn't. When S8.4 lands, set `min_machines_running = 1` or run jobs on their own machine.

## Options compared

| | Vercel (Hobby) | Render | Railway | **Fly.io** |
| --- | --- | --- | --- | --- |
| Monthly cost for our API | $0, for personal, non-commercial use only | $0 on the free tier (no disk; sleeps). $7 for Starter (0.5 CPU, 512 MB), plus $0.25 per GB of disk. | $5 for Hobby, which includes $5 of usage. 512 MB always on uses all $5 ($10 per GB of RAM). | $3.69 for `shared-cpu-1x` with 512 MB always on, plus $0.15 per GB of volume, and less with auto-stop. A card is required. |
| Where the data lives | No disk. The store would be bundled at build time (data can't come from git) or read from object storage. | A disk, on paid instances only | A volume, up to 5 GB on Hobby | A volume |
| Request time limit | 300 s on Hobby; 800 s on Pro | 100 minutes (staff answer) | 15 minutes (staff answer) | No cap. The proxy reportedly drops a connection idle for 60 s. |
| Cold start | On each scale-up, Python imports DuckDB and pandas | Free tier: about a minute after 15 idle minutes. Paid: none. | None: always on | 7.2 s after auto-stop (measured); none if a machine stays up |
| Long-running work | Needs Vercel Workflows or Queues | A background worker | A background worker | A background task in the API, or a machine started per job |
| Five people | Team features need Pro: $20 per developer seat | Hobby allows one member. Pro: $25 a month for unlimited members. | Hobby is for one developer. Pro: $20 a month and up. | Organization members at no charge |
| Python 3.14 | Supported | Through Docker | Through Docker | Through Docker (deployed) |

**Data in object storage** (S3, R2, or Supabase Storage) works with any host. The API would download the store at startup or query it remotely with DuckDB's `httpfs` extension. That adds startup time or per-query latency, and another place where Tiingo's data must stay private. With a store of a few megabytes, perhaps 150 MB later, a volume is simpler. Revisit this if the API ever needs more than one machine.

**Why not the others:**

- **Vercel**'s free plan is non-commercial and single-user. It has no disk, caps requests at 5 minutes, and needs extra services for background work.
- **Render** is the easiest to use, but its free tier sleeps and has no disk, and a disk plus team access costs about $32 a month.
- **Railway** is close to Fly, but its Hobby plan is for one developer, and its 15-minute request cap matters less than the missing team access.

## Re-evaluation, 2026-10-29: one owner, AWS Lambda, and Cloudflare

Two things changed after D4:

- **The team is fine with one person owning the hosting on a personal plan.** That removes the five-seat requirement that counted against Render's and Railway's personal plans.
- **The professors suggested AWS Lambda and Cloudflare.**

Prices and limits were checked on 2026-10-29. The costs are for our API: low traffic, a store of a few megabytes, and occasional backtests.

| | Fly.io (deployed) | Railway Hobby | Render Hobby + Starter | Vercel Hobby | AWS Lambda | Cloudflare |
| --- | --- | --- | --- | --- | --- | --- |
| Monthly cost | Under $1 with auto-stop; $3.84 always on | $5, which includes $5 of usage. Our app (about 150–250 MB of RAM) should use about $2 of it. | $7.25: Starter (0.5 CPU, 512 MB), plus a 1 GB disk | $0 (personal, non-commercial) | About $0: 1M requests and 400,000 GB-seconds are free each month. A new account's free plan closes after 6 months unless it moves to the paid plan. | $5 for Workers Paid, which includes 25 GiB-hours of memory and 375 vCPU-minutes for Containers |
| CPU for a backtest | Throttled to 6.25% once the burst balance is spent; a dedicated CPU is $33 a month | Each replica can use up to 8 vCPU, billed for active use. No baseline share or credits are documented. | Half a CPU, always | 1 vCPU, at most 300 s per request | Up to 6 vCPU (at 10 GB), at most 15 minutes per invocation, billed per use | Workers can't run our stack (below). Containers: up to 4 vCPU. |
| The store | A volume (deployed) | A volume, with CLI upload | A disk | None; fetched from storage at each cold start | None; fetched from S3 into `/tmp` at each cold start | Containers: none; fetched from R2 at each start |
| Cold starts | 7.2 s after auto-stop (measured) | None: always on within the $5 (sleeping after 10 idle minutes is optional) | None | On each scale-up | On each scale-up, with DuckDB and pandas to import (not measured) | Containers sleep between requests, with a cold start on wake |
| Deploys | Command line; GitHub needs an Action | From GitHub on merge, built in | From GitHub on merge | From GitHub on merge | SAM, CDK, or the CLI; GitHub needs an Action with AWS credentials | Wrangler, plus a Worker and a Durable Object in TypeScript in front of the container |
| Background backtests (S8.4) | A task in the API process | A task in the API process | A task in the API process | Needs Vercel Workflows or Queues | An asynchronous invocation, with job state kept in S3 or DynamoDB | A container per job, routed by a Durable Object |
| Effort to move | None | Blocked: new sign-ups paused since a security incident on 2026-10-21 (below) | Low: the same Dockerfile | Medium | High | High |

**AWS Lambda.**

- **Strengths:** it's the cheapest option, and each invocation gets as much CPU as its memory setting buys.
- **What it would need:**
  - an adapter for FastAPI (Lambda's newer Web Functions, which run an ordinary HTTP server, support only Node.js);
  - the store in S3;
  - job state in S3 or DynamoDB for background backtests;
  - IAM, a container registry, and CloudWatch to run it all.
- **Verdict on 2026-10-29:** too much new infrastructure for a five-person team with full sprints. It's worth another look for CISC 499's parameter sweeps (S14.2), which would fan out well across Lambda invocations. *Revisited on 2026-10-31:* the owner is willing to do the setup, so Lambda now leads ([plan](#plan-2026-10-31-try-aws-lambda-first-with-fly-as-the-fallback)).

**Cloudflare.**

- **Workers can't run the API.** Workers allow 128 MB of memory per isolate, a 64 MiB bundle, and 1 second to start. Python Workers can only use pure-Python or Pyodide-built packages, and DuckDB isn't confirmed among them.
- **Containers can run it, with costs.** They need a Worker and a Durable Object in front, written in TypeScript, and keep no disk, so the store would live in R2. A 1 GiB instance uses up the included memory hours in about a day, so it's meant to sleep, with a cold start on each wake.
- **R2 is still useful.** With 10 GB free and no egress fees, it's a good home for a master copy of the store, whatever the host.

**Correction to the table above:** Railway bills the memory actually used, not a fixed 512 MB. Our app uses about $2 of the $5, not all of it.

**The others.**

- **Vercel** is free and sits next to the frontend, but has no long-running process for background backtests.
- **Render** is the easiest to run, but gives half a CPU for $7.25.

**Railway Hobby** fixes Fly's weak point for about $1 a month more than Fly's always-on machine. Its CPU isn't held to a baseline share, so backtests, and CISC 499's sweeps, run at full speed for cents each. It also deploys from GitHub on merge, which is still an S15.1 task on Fly.

**Railway can't be used now.**

- **The incident.** On 2026-10-21 an intruder reached Railway's internal systems and decrypted some customers' environment variables, in at most 1.85% of workspaces, about 100,000 ([preliminary report](https://blog.railway.com/p/preliminary-report-october-security-incident)).
- **Railway's response.** It hasn't ruled out access to source code. It recommends rotating every secret stored there, and it has paused new sign-ups with no reopening date ([status page](https://status.railway.com/)).
- **Our attempt.** We tried to sign up on 2026-10-29 to measure it and were refused.
- **Why it matters later.** Our host will hold secrets: the sign-in verification secret (S16.4) and the AI assistant's API key (CISC 499).

**Recommendation on 2026-10-29, superseded on 2026-10-31 by the [plan](#plan-2026-10-31-try-aws-lambda-first-with-fly-as-the-fallback) below: stay on Fly.io, and add the card when a host is needed again, before S8.4 (Sprint 4).** Sprint 3 runs locally, so the trial can lapse on 2026-10-31. Fly's weak point, CPU throttling, has fixes inside Fly that cost cents per backtest, and they still apply if Fly stays the fallback:

1. **Batch the engine's reads (S7.3, S15.2).** That cuts a backtest's CPU work by orders of magnitude.
2. **Keep one machine running when S8.4 lands** ($3.69 a month), so its burst balance builds up to about 8 minutes at full speed.
3. **For sweeps or heavy runs, start a `performance-1x` machine per job,** billed by the second.

Revisit this only if S8.4's measured timings still don't fit. Then try Render's fixed CPU first, or Railway once sign-ups reopen and its final report is out.

## Plan, 2026-10-31: try AWS Lambda first, with Fly as the fallback

Three things changed after the re-evaluation:

- **A budget limit.** The owner will pay at most $5 a month. That rules out Render's Starter ($7.25 with a disk) and a Fly machine with a dedicated CPU kept running ($33).
- **More setup is fine, if it's worth it.** The re-evaluation set Lambda aside for its setup work alone.
- **A professor recommends Lambda.** It's widely used, especially for work that comes in bursts, as ours does.

**Why Lambda now leads:**

- **It costs a few cents a month.** Lambda's always-free allowance is 1 million requests and 400,000 GB-seconds a month. A 7-minute backtest at 2 GB uses 840 GB-seconds, so about 470 runs a month are free. The store in S3, the image in the container registry, and the logs cost cents.
- **Its CPU isn't throttled.** A function gets one vCPU at 1,769 MB of memory, and up to 6 at 10,240 MB, for as long as it runs. Fly's shared CPU drops to 6.25% once its burst is spent.
- **15 minutes per run is enough.** Our worst case, the unbatched workload above, takes about 7 minutes on one full-speed CPU. Once the engine batches its reads, a backtest takes seconds. A CISC 499 sweep (S14.2) runs one invocation per variant, all at once, instead of one long run.

**What stays the same:**

- **DuckDB and Parquet.** DuckDB is a library inside our process, not a server, so it runs in Lambda unchanged. The store is read-only between ingestions: each new Lambda environment copies it from a private S3 bucket into `/tmp` when it starts, well under a second at today's 1.2 MB. With no database server, there are no connections to pool.
- **Supabase** for accounts and the run registry (D9, D10), reached through its connection pooler.
- **The Dockerfile.** AWS's [Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter) runs our FastAPI app as it is, on the same port, 8080. It has to be a container image, because our installed packages (279 MB) are over Lambda's 250 MB limit for a zip upload.

**What's new to build:**

- A private S3 bucket for the store, and a step that copies it into `/tmp` at startup.
- A function URL with CORS for the API. API Gateway's HTTP API cuts every request off at 30 seconds, so it isn't used.
- Background backtests (S8.4). The API starts a run as an asynchronous invocation, which the adapter forwards to the app. The run writes its status and results to the run registry, and the page polls it.
- An IAM role, a container registry (ECR) repository, and CloudWatch logs.
- Deploys from GitHub Actions, signing in to AWS with OIDC, so no long-lived keys sit in GitHub.
- A budget alert at $5. AWS has no hard spending cap.

**The spike, before S8.4 (Sprint 4, from 2026-11-09):**

1. **The owner creates the AWS account.** The free plan closes after 6 months, and we need hosting until May 2027, so move it to the paid plan with a card and set the budget alert.
2. **Deploy** the same image with the adapter, a function URL, and the store in S3.
3. **Measure:**
   - the cold start (the first request after an idle spell), warm lookups, and the copy from S3;
   - `spikes/hosting.py`'s full 100-ticker workload at 1,769 MB and at about 5,300 MB (one and three vCPU), with peak memory.

   Then turn the measured GB-seconds into a monthly cost.
4. **Decide.**
   - **Move to Lambda** and record a new D4 entry if lookups are fine after a cold start, the full workload finishes well inside 15 minutes, and the monthly cost stays under $5.
   - **Otherwise,** add the card to Fly and redeploy there ([steps](#deploying-and-updating-from-backend)), which takes about 15 minutes.

**Until then, develop locally, and keep the backend ready for either host:**

1. **Make a backtest a plain function,** such as `run_backtest(run_id)`, that reads its spec and writes its status and results to the run registry. It then runs the same way as a background task on Fly or as a Lambda invocation.
2. **Batch the engine's reads (S7.3, S15.2).**
3. **Keep the API stateless and the store read-only,** as they are now.

**For CISC 499:** the chat assistant streams its answers, and the MCP server keeps connections open. Lambda supports both, through response streaming on a function URL and MCP's stateless Streamable HTTP, but they fit a container more naturally. Check when E10 and E11 start.

**Railway** comes back into question only if its sign-ups reopen. Its Hobby plan is $5 a month, but its hard spending cap starts at $10, so it can't guarantee the $5 limit.

## Cost and the trial

- **The trial** started 2026-10-24 (UTC) and lapsed on 2026-10-31. While it ran, it stopped each machine after 5 minutes of running.
- **The card is deferred.** On 2026-10-29 the team chose to add a card only when a host is needed again, before S8.4 (Sprint 4). Sprint 3 needs no hosting, since tests run on fixtures and everyone develops against a local backend.
  - Since the trial lapsed, the URL doesn't answer, and Fly may remove the machine and the volume.
  - Nothing is lost: the Dockerfile and `fly.toml` are in git, and the store comes from ingesting. With a card added, redeploying takes the [steps below](#deploying-and-updating-from-backend), about 15 minutes.
- **With a card** the deployment costs at most about $3.84 a month:
  - $3.69 for the machine, if it never stopped;
  - $0.15 for the volume;
  - $0.15 per GB-month for a stopped machine's root filesystem.

  Anything beyond that, such as a dedicated machine for backtests (S8.4) or a bigger volume, is billed to the same card. The owner's limit is $5 a month in all, so agree on it as a team first.

## The deployment

- **App:** `quant-time-machine-api` in `iad`, on one `shared-cpu-1x` machine with 512 MB, which auto-stops when idle. The measured peak, 303 MB on a Mac for the full workload, fits. Raise it to 1 GB if a real backtest needs more.
- **Volume:** `qtm_data`, 1 GB, mounted at `/data`. Only `DATA_DIR/store` is uploaded, never the raw cache.
- **Environment:**
  - `DATA_DIR=/data`;
  - `CORS_ORIGINS` for `http://localhost:3000` and the Vercel site;
  - `SERVE_RAW_PRICES` deliberately unset, so `/v1/prices` answers 403. Tiingo's prices sit on the volume for internal use and are never served (D2).
- **No API keys on the host:** serving needs none, and ingestion runs on a laptop.
- **The build context:** `.dockerignore` keeps `data/` and `.env` out of it, since flyctl doesn't filter by git. The context was 377 kB, all code.

### Deploying and updating (from `backend/`)

First time only:

```bash
brew install flyctl
fly auth login
fly apps create quant-time-machine-api
fly volumes create qtm_data --region iad --size 1
```

Each deploy:

```bash
fly deploy --remote-only --ha=false
```

To upload or replace the store after ingesting locally:

```bash
COPYFILE_DISABLE=1 tar --no-xattrs -czf /tmp/store.tgz -C data store
fly ssh sftp put /tmp/store.tgz /data/store.tgz
fly ssh console -C "sh -c 'cd /data && rm -rf store.new && mkdir store.new && tar -xzf store.tgz -C store.new --strip-components=1 && rm -rf store.old && (mv store store.old || true) && mv store.new store && rm -rf store.old store.tgz'"
```

- **The swap is safe while serving.** The new store is unpacked beside the old one and swapped in with a rename. The API opens the files on each request, so it simply picks up the new store.
- **To check a deploy:** `curl https://quant-time-machine-api.fly.dev/health` and `fly logs`.
- **To measure on the host:** `fly ssh console -C "sh -c 'cd /app && .venv/bin/python -m spikes.hosting --data-dir /data'"` runs the spike there.

## Next steps for S15.1

- [ ] Before S8.4 (Sprint 4, from 2026-11-09) needs a host, run the AWS Lambda spike in the [plan](#plan-2026-10-31-try-aws-lambda-first-with-fly-as-the-fallback), and record a new D4 entry with its measurements. If Lambda doesn't fit, add the card to Fly and redeploy. The trial lapsed on 2026-10-31.
- [ ] Deploy from GitHub Actions on merges to `main`:
  - on Lambda, sign in to AWS with OIDC;
  - on Fly, use a deploy token (`fly tokens create deploy`) as a repository secret and `flyctl deploy --remote-only`.
- [ ] Set `NEXT_PUBLIC_API_URL` on Vercel to the API's URL, and add any preview origins the frontend needs to `CORS_ORIGINS`.
- [ ] Write a smoke test for after each deploy: `/health`, a macro value, a filing, and prices answering 403.
- [ ] Script the store upload above, until ingestion runs on a schedule (S15.5).
- [ ] Upload the universe v1 store (S6.5, ingested 2026-10-31) to whichever host the D4 decision picks. Copy all of `DATA_DIR/store`, including `_versions/`, the data-version manifests (S3.7), so the API serves and echoes the same versions as the machine that ingested. On Lambda, that's the private S3 bucket; the Fly commands above already copy the whole folder.
- [ ] Run the container as a non-root user.
- [ ] With S8.4's real timings, pick the backtest memory size on Lambda, or the backtest CPU and `min_machines_running` on Fly.
- [ ] Keep `SERVE_RAW_PRICES` unset until D2's display rights are settled.

## Sources

Retrieved 2026-10-23:

- **Fly.io:** [pricing](https://docs.fly.io/about/pricing), [CPU performance](https://docs.fly.io/machines/cpu-performance), [volumes](https://docs.fly.io/launch/volume-storage), [configuration](https://docs.fly.io/reference/configuration), and a [forum answer on proxy timeouts](https://community.fly.io/t/request-timeouts-on-fly-io/5653).
- **Vercel:** [function limits](https://vercel.com/docs/functions/limitations), [Python runtime](https://vercel.com/docs/functions/runtimes/python), and the [Hobby plan](https://vercel.com/docs/plans/hobby).
- **Render:**
  - [free instances](https://render.com/docs/free), [disks](https://render.com/docs/disks), [workspace plans](https://render.com/docs/new-workspace-plans), and [pricing](https://render.com/pricing);
  - [Pro's flat price](https://render.com/changelog/updated-plans-for-render-workspaces), and a [forum answer on the 100-minute timeout](https://community.render.com/t/need-to-increase-requests-timeout-of-5-minutes/4001).
- **Railway:** [plans](https://docs.railway.com/pricing/plans), [resource prices](https://docs.railway.com/reference/pricing), and a [staff answer on the 15-minute timeout](https://station.railway.com/questions/increase-max-http-timeout-1c360bf9).

Retrieved 2026-10-29, for the re-evaluation:

- **Railway:** [scaling](https://docs.railway.com/reference/scaling), [Railway compared with Fly](https://docs.railway.com/platform/compare-to-fly), [app sleeping](https://docs.railway.com/reference/app-sleeping), [volume uploads](https://docs.railway.com/cli/volume), and a [staff answer on per-replica limits](https://station.railway.com/questions/hobby-plan-1048ca8f).
- **Railway's incident:** the [preliminary report](https://blog.railway.com/p/preliminary-report-october-security-incident), the [status page](https://status.railway.com/) (sign-ups still paused at 15:45 UTC on 2026-10-29), and [The Hacker News](https://thehackernews.com/2026/10/railway-says-intruder-may-have-accessed.html).
- **AWS:** [Lambda pricing](https://aws.amazon.com/lambda/pricing/), [quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html), [runtimes](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html), [Web Function runtimes](https://docs.aws.amazon.com/lambda/latest/dg/web-functions-runtimes.html), and the [Free Tier](https://aws.amazon.com/free/).
- **Cloudflare:** [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [Python packages](https://developers.cloudflare.com/workers/languages/python/packages/), [Containers pricing](https://developers.cloudflare.com/containers/pricing/), and [Containers limits](https://developers.cloudflare.com/containers/platform-details/limits/).

Retrieved 2026-10-31, for the plan:

- **AWS:** [Lambda timeouts](https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html), [API Gateway HTTP API quotas](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html), and the [Lambda Web Adapter](https://github.com/awslabs/aws-lambda-web-adapter).
- **Render:** [compute plans](https://render.com/docs/compute-plans).
- **Railway:** [cost control](https://docs.railway.com/pricing/cost-control) and the [usage CLI](https://docs.railway.com/cli/usage).
