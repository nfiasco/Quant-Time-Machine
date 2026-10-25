# Backend and data hosting (decision D4)

> **Spike S1.6.** Decided 2026-10-23, pending team review. The measurements come from [`backend/spikes/hosting.py`](../backend/spikes/hosting.py), run on the real M2 store (ingested 2026-10-23) on a laptop and on the deployed machine. Prices and limits were checked on 2026-10-23. They change, so check them again before S15.1.

## Decision

**The API runs on Fly.io.** It's a container built from [`backend/Dockerfile`](../backend/Dockerfile), on one shared-CPU machine in Ashburn, Virginia (`iad`), with the point-in-time store on a 1 GB volume at `/data`. The configuration is [`backend/fly.toml`](../backend/fly.toml).

- **Deployed** at <https://quant-time-machine-api.fly.dev> (try `/docs`), on Fly's free trial until the team adds a card ([Cost and the trial](#cost-and-the-trial)).
- **Why Fly:**
  - **A disk for the store,** which changes only when we ingest. Vercel has no disk, and Render's free tier has none.
  - **A long-lived process,** which backtests need (S8.4). Vercel caps a request at 300 seconds on Hobby, and background work there needs extra services.
  - **No seat fees for the five of us.** Vercel's team features cost $20 per developer seat. Render's free workspace allows one member, and its Pro plan is $25 a month. Railway's Hobby plan is for one developer.
  - **The cheapest always-available option with a disk:** at most about $4 a month, and less with auto-stop.
  - **A container,** so production runs our exact Python 3.14 and `uv.lock`. `fly deploy` builds on Fly's servers, so nobody needs Docker installed.
- **What we accept:**
  - Fly needs a card; the trial ends after 7 days or 2 hours of machine time.
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
- **The full 100-ticker run couldn't finish on Fly,** because the trial stops a machine after 5 minutes, so its times are extrapolated per read.

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

## Cost and the trial

- **The trial** started 2026-10-24 (UTC). It ends after 7 days or 2 hours of machine time, whichever comes first, and it stops each machine after 5 minutes of running.
  - The API keeps answering, because the next request restarts the machine.
  - Anything longer than 5 minutes, such as the full workload, can't finish.
- **With a card** the deployment costs at most about $3.84 a month:
  - $3.69 for the machine, if it never stopped;
  - $0.15 for the volume;
  - $0.15 per GB-month for a stopped machine's root filesystem.

  The team decides whether to add one. Add it at <https://fly.io/trial> before the trial ends, or the URL stops working.

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

- [ ] Add a card, or move hosts, before the trial ends (a team decision).
- [ ] Deploy from GitHub Actions on merges to `main`, with a deploy token (`fly tokens create deploy`) as a repository secret and `flyctl deploy --remote-only`.
- [ ] Set `NEXT_PUBLIC_API_URL` on Vercel to the Fly URL, and add any preview origins the frontend needs to `CORS_ORIGINS`.
- [ ] Write a smoke test for after each deploy: `/health`, a macro value, a filing, and prices answering 403.
- [ ] Script the store upload above, until ingestion runs on a schedule (S15.5).
- [ ] Run the container as a non-root user.
- [ ] With S8.4's real timings, pick the backtest CPU and `min_machines_running`.
- [ ] Keep `SERVE_RAW_PRICES` unset until D2's display rights are settled.

## Sources

Retrieved 2026-10-23:

- **Fly.io:** [pricing](https://docs.fly.io/about/pricing), [CPU performance](https://docs.fly.io/machines/cpu-performance), [volumes](https://docs.fly.io/launch/volume-storage), [configuration](https://docs.fly.io/reference/configuration), and a [forum answer on proxy timeouts](https://community.fly.io/t/request-timeouts-on-fly-io/5653).
- **Vercel:** [function limits](https://vercel.com/docs/functions/limitations), [Python runtime](https://vercel.com/docs/functions/runtimes/python), and the [Hobby plan](https://vercel.com/docs/plans/hobby).
- **Render:**
  - [free instances](https://render.com/docs/free), [disks](https://render.com/docs/disks), [workspace plans](https://render.com/docs/new-workspace-plans), and [pricing](https://render.com/pricing);
  - [Pro's flat price](https://render.com/changelog/updated-plans-for-render-workspaces), and a [forum answer on the 100-minute timeout](https://community.render.com/t/need-to-increase-requests-timeout-of-5-minutes/4001).
- **Railway:** [plans](https://docs.railway.com/pricing/plans), [resource prices](https://docs.railway.com/reference/pricing), and a [staff answer on the 15-minute timeout](https://station.railway.com/questions/increase-max-http-timeout-1c360bf9).
