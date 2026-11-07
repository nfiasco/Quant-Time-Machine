# Backend and data hosting (decision D4)

> **Spike S1.6.** Decided 2026-10-23, pending team review. The measurements come from [`backend/spikes/hosting.py`](../backend/spikes/hosting.py), run on the real M2 store (ingested 2026-10-23) on a laptop and on the deployed machine. Prices and limits were checked on 2026-10-23. They change, so check them again before S15.1. Updated 2026-10-29: the team deferred the card until a host is needed, before S8.4 (Sprint 4). The free trial lapsed on 2026-10-31, and Sprint 3 runs locally. Also re-evaluated on 2026-10-29, with one owner allowed and AWS Lambda and Cloudflare added ([re-evaluation](#re-evaluation-2026-10-29-one-owner-aws-lambda-and-cloudflare)). Updated 2026-10-31: with a $5-a-month limit and the owner willing to do the setup, AWS Lambda is the lead candidate. A spike before S8.4 decides, with Fly as the fallback ([plan](#plan-2026-10-31-try-aws-lambda-first-with-fly-as-the-fallback)). **Decided 2026-11-06: Railway's Hobby plan** ([decision](#decision-2026-11-06-railway)), after Railway reopened sign-ups on 2026-11-02. It replaces both the Fly decision and the Lambda plan, and Google Cloud Run's free tier is the way out if paying stops being worth it. **Measured against Cloud Run the same day** with the same image ([benchmark](#railway-vs-cloud-run-measured-2026-11-06)): the decision stands.

## Decision, 2026-11-06: Railway

**The API will run on Railway's Hobby plan:** $5 a month, which includes $5 of usage, on the owner's personal account. Railway builds the same [`backend/Dockerfile`](../backend/Dockerfile) from GitHub and redeploys it on each merge to `main`. This replaces the [Fly.io decision](#original-decision-2026-10-23-flyio) and the [Lambda plan](#plan-2026-10-31-try-aws-lambda-first-with-fly-as-the-fallback). Nothing is deployed yet: S15.1 (Sprint 5) sets it up ([next steps](#next-steps-for-s151)).

- **Why Railway:**
  - **No cold starts.** The service stays on, so the first request after a quiet spell is as fast as any other. Cloud Run and Lambda scale to zero: Cloud Run took 5.6–14 s to answer the first request after scaling to zero ([measured](#railway-vs-cloud-run-measured-2026-11-06)), and Fly took 7.2 s after auto-stop.
  - **Faster.** The same image answered 1.6–3.7× faster than on Cloud Run, and ran the backtest-shaped workload 2–4× faster.
  - **CPU after the response.** S8.4 can run a backtest in a background thread after `POST /v1/backtests` answers, "without extra infrastructure," as the story asks. Cloud Run's free billing mode gave such a thread 0.3% of a CPU, and Lambda freezes an environment once it answers, so both would need a queue or a second invocation.
  - **No time limit on background work.** A web request stops at 15 minutes while it sends data and at 5 minutes if it sends nothing (both measured), but a background run doesn't. Lambda stops every invocation at 15 minutes.
  - **Unthrottled CPU:** up to 48 vCPU and 48 GB per service on Hobby, billed by use, with no documented baseline share or burst credits. Fly's shared CPU drops to 6.25% once its burst balance is spent.
  - **Deploys from GitHub on merge,** which S15.1 would otherwise build as a GitHub Action.
  - **Inside the $5 limit.** Idle, the API used 150–180 MB and 0.002 vCPU on Railway, about $1.85 a month, so expected use comes to about $2–3 of the included $5.
- **What we accept:**
  - **$5 a month for as long as it runs,** where Cloud Run or Lambda would cost about $0. The hard usage limit can't go below $10, so set it to $10, with an email alert at $5.
  - **Railway's security incident.** On 2026-10-21 an intruder decrypted some customers' environment variables ([re-evaluation](#re-evaluation-2026-10-29-one-owner-aws-lambda-and-cloudflare)). Railway reopened sign-ups on 2026-11-02, for paid plans only, and marked the incident resolved, but it hadn't published a final report by 2026-11-06. The repository is public, so only the host's secrets are at stake. Keep them few and narrowly scoped, and rotate them if Railway reports anything new.
  - **One developer.** Hobby is a one-person plan, so only the owner sees the dashboard and logs. Deploys happen on merge, so nobody else needs access to deploy.
  - **Network blocks.** On 2026-11-05 Railway's status page reported outside networks blocking its IP addresses. Check that the API answers on campus Wi-Fi before a demo.
- **The way out: Google Cloud Run's free tier,** if paying stops being worth it, for example after graduation. It runs the same Dockerfile unchanged and costs about $0 at our traffic. To keep that move to about a day's work:
  - keep a backtest a plain function, such as `run_backtest(run_id)`, that reads its spec and writes its status and results to the run registry, so a thread on Railway and a Cloud Tasks request on Cloud Run can both call it;
  - keep the API stateless and the store read-only;
  - batch the engine's reads (S7.3, S15.2).

### Railway vs Cloud Run, measured 2026-11-06

Before committing, we deployed the same image to both and measured them side by side with [`backend/spikes/host_compare/`](../backend/spikes/host_compare/). The image was `backend/Dockerfile` with the universe store baked in and a thin wrapper that adds timing routes: every `/v1` route was the real one, and prices still answered 403. Each service got 1 vCPU and 1 GB in northern Virginia (us-east4): Railway on its trial plan, and Cloud Run with request-based billing (the mode with the free tier), startup CPU boost, and sign-in required. The client was a laptop in Delaware.

| Measure | Railway | Cloud Run |
| --- | --- | --- |
| First request after idling (first byte) | 1.9–2.9 s waking from sleep; none if kept on | 5.6–14 s |
| App start inside the container | 1.2–1.8 s | 4.8–12.6 s |
| Health check, warm (median) | 19 ms | 30 ms, 33 ms |
| Macro lookup, warm (median) | 51 ms | 94 ms, 81 ms |
| Snapshot, the heaviest route (median) | 723 ms | 2,656 ms, 1,668 ms |
| Backtest-shaped workload, 10 tickers | 70 s | 266 s, 140 s; 117 s as a Cloud Run job |
| Macro lookups per second with 100 in flight | 18, on one replica | 56 and 84, on 5 instances |
| CPU-bound requests per second with 50 in flight | 16 on one replica, 36 on two | 42 and 33, on 5 instances |
| A request that sends nothing | Cut at 300 s (502) | Cut at 3,600 s (504) |
| A request that streams | Cut at 900 s | Cut at 3,600 s |
| CPU for a thread after the response | Full speed | 0.3%; 98% with instance-based billing |
| Back after the process exits | 3.5 s, with three 502s | 1.4 s, with one 503 |
| Back after running out of memory | 3.0 s; that request got a 502 | The request finished, then the instance was replaced with no errors |
| Requests dropped during a redeploy | None of 1,253 | None of 1,187 |
| Deploy from source | 46 s first, 43 s after a change | 108 s first, 132 s after a change; 15 s for an image already built |

Where Cloud Run has two values, they're gen1 then gen2, its two sandboxes; its other rows are gen1, the default.

- **Railway was faster on every route,** by 1.6–3.7× per request and 2–4× on the workload. It runs on newer CPUs (AMD EPYC 9655, Zen 5) with no sandbox in the way. Cloud Run's gen1 sandbox (gVisor) slows Python's imports and DuckDB's file reads, and gen2 is a microVM on Zen 3 CPUs. Cloud Run also showed DuckDB 2 or 6 CPUs for 1 vCPU, so it ran two threads. Railway's trial vCPU is shared and Hobby's is dedicated, so Hobby should do at least as well.
- **Cold starts are Cloud Run's real cost for us.** It keeps an idle instance for at most 15 minutes, and at a class project's traffic most visits come later than that, so most visitors would wait 6–14 s. Railway kept on makes nobody wait, and even asleep it woke in under 3 s.
- **Background backtests need Railway, or Cloud Run's paid billing mode.** Under request-based billing, a thread got 0.3% of a CPU once its request returned. Instance-based billing gives it the CPU, but an always-on instance then costs about $45 a month. On Cloud Run, a backtest belongs in a Cloud Run job (up to 168 hours a task) or inside a request (up to 60 minutes).
- **Railway's request limits match its docs:** 15 minutes while data flows, and 5 minutes with none. S8.4's background runs aren't requests, so they don't hit them, but no request can hold a run open longer than that.
- **Scaling:** Cloud Run added instances on its own and served 2–5× Railway's throughput at high concurrency, with 99th percentiles of 4–6 s while new instances started. Railway stays on its replicas until we add more by hand, two on the trial and six on Hobby, and a second replica answered 39 s after we asked. Our traffic is far below either limit.
- **Both recovered from crashes in seconds and dropped nothing during redeploys.** Cloud Run promises 99.95% monthly uptime. Railway offers no SLA below Enterprise, and in 2026 it had an eight-hour outage (May 19), a US East outage (July 2), five minutes of 404s for every domain (September 30), and the security incident (October 21).

Estimated monthly bill, from published prices and our measured memory and CPU:

| Workload | Railway Hobby | Cloud Run, scaling to zero | Cloud Run, one warm instance |
| --- | ---: | ---: | ---: |
| Quiet month: 5,000 requests, 20 backtests | $5.00, using $1.85 of the included $5 | $0.00 | $4.75 |
| Active development: 50,000 requests, 200 backtests | $5.00 ($1.99) | $0.00 | $5.48 |
| Demo week: 500,000 requests, 1,000 backtests | $5.00 ($2.74) | $0.36 | $9.37 |
| Busy: 2 million requests, 3,000 backtests | $5.00 ($4.90) | $11.90 | $20.57 |

- **Assumptions:** Railway always on, at 180 MB and 0.002 vCPU idle, 0.06 vCPU-seconds a request, and 68 CPU-seconds a backtest (the 10-ticker workload). Cloud Run at 1 vCPU and 512 MiB, each request billed alone for 0.15 s (billing rounds up to 100 ms), 7 s per cold start, and backtests as Cloud Run jobs at 1 GiB. Google applies the free tier as a discount of about $5.22 a month: $4.32 of CPU and $0.90 of memory.
- **A warm instance avoids most cold starts but still gets no CPU between requests,** and Google may restart it at any time.
- **Cloud Run instances,** in preview since August 2026, run one always-on container for $5.70 a month at 1 vCPU and 1 GiB, but on a shared CPU with a burst budget, the model that throttled backtests on Fly.

**What it means for D4: the decision stands.** Railway is the better host for this API while we pay for it: faster, no cold starts, and CPU for background runs. Cloud Run stays the way out, and the benchmark shows the move works: the same Dockerfile ran there unchanged, at the cost of 6–14 s cold starts and slower requests. Two things follow ([next steps](#next-steps-for-s151)): add a personal login to the Railway account before graduation, and consider keeping a Cloud Run copy as a free standby for demo days, since it costs nothing while idle.

### What we measured, 2026-11-06

On an Apple-silicon Mac, with the universe v1 store (S6.5, with S5.5's XBRL facts): 376,274 rows in 234 Parquet files, 8.3 MB. As one `tar.gz` it's 7.5 MB, which unpacks in 0.04 s.

| `spikes/hosting.py` workload: 192 decisions, 100 tickers | Per read | Total |
| --- | ---: | ---: |
| DuckDB's default threads (about 4.4 cores busy), measured | 6.59 ms | 256 s |
| One DuckDB thread, as on one vCPU (measured with 10 tickers) | 8.76 ms | About 5.7 minutes |
| One thread, with the store rewritten as one Parquet file per table | 5.83 ms | About 3.8 minutes |
| One thread, with DuckDB's `parquet_metadata_cache` on | 6.99 ms | About 4.5 minutes |

- **Reads got slower as the store grew.** The same workload took 150 s on the M2 store, which had 24 files ([below](#a-backtest-shaped-workload)). Most of the cost is per query, not per byte: one file per table saves a third, and the metadata cache a fifth. Batching the engine's reads (S7.3, S15.2) is the real fix, on any host.
- **On one server vCPU, expect about twice the one-thread time.** In the Fly measurements, a full-speed server vCPU ran this about 2× slower than a Mac core, so the unbatched run would take about 11–12 minutes. That's fine as a background task on Railway, tight under Lambda's 15 minutes, and far from NFR-5's 60 seconds.
- **Peak memory** was 330 MB with the default threads and 155 MB with one.
- **The one-thread runs** wrapped `spikes.hosting` so that every connection `app.data.store.connect()` opens sets `threads = 1`, plus `parquet_metadata_cache = true` for the last row.
- **Serverless hosts stay possible.** The API answered `/health` and six `/v1` lookups from a read-only working directory with no home directory, as on Lambda: 14–57 ms each in process, and 286 ms for the first snapshot. The DuckDB extensions the app uses (`parquet`, `icu`, `json`, and `core_functions`) are built into the 1.5.6 Python package, so nothing downloads at runtime.

### Options compared, 2026-11-06

Prices and limits were checked on 2026-11-06, for our API's low traffic.

| Option | Monthly cost for our API | Why not |
| --- | --- | --- |
| Google Cloud Run | About $0: 2M requests, 180,000 vCPU-seconds, and 360,000 GiB-seconds are free each month | It scales to zero: the first request after that took 5.6–14 s, and the same code ran 1.6–3.7× slower than on Railway ([measured](#railway-vs-cloud-run-measured-2026-11-06)). A warm minimum instance costs about $5–10 a month. Its free billing mode gives no CPU between requests, so background runs need a Cloud Run job or Cloud Tasks. It's the way out above. |
| Cloud Run instances | $5.70 for one always-on instance with 1 vCPU and 1 GiB | In preview since August 2026, on a shared CPU with a burst budget, the model that throttled backtests on Fly |
| AWS Lambda | About $0: 1M requests and 400,000 GB-seconds are free each month | The [plan](#plan-2026-10-31-try-aws-lambda-first-with-fly-as-the-fallback)'s new infrastructure, a 15-minute cap, and one request per environment, so more cold starts. A container function unused for a few weeks goes inactive and rejects the first request. |
| ECS on Fargate | About $9 for the smallest always-on task (0.25 vCPU, 0.5 GB), plus $3.65 for a public IPv4 address or about $16 for a load balancer | No free tier |
| AWS Batch | Nothing itself; its jobs pay Fargate or EC2 rates | It's a queue for large batches of jobs, and S14.2's sweeps are about nine runs |
| AWS Step Functions | $0: 4,000 state transitions are free each month | It chains Lambda steps past 15 minutes, which batched reads don't need |
| Compute Engine e2-micro | $0: one always-free VM | We'd maintain the server, HTTPS, and updates ourselves, on about a quarter of a CPU |
| Cloudflare | $5 for Workers Paid | Workers can't run the stack ([re-evaluation](#re-evaluation-2026-10-29-one-owner-aws-lambda-and-cloudflare)). Containers sleep to stay inside the $5, or cost about $12 a month always on for a quarter of a CPU. |
| Fly.io | About $4 | Throttled shared CPU. No longer the fallback since 2026-11-01. |

### If it stays up after graduation

- **Move to Cloud Run's free tier** if $5 a month stops being worth it ([the way out](#decision-2026-11-06-railway)). The image ran there unchanged; expect 6–14 s for the first request after a quiet spell ([measured](#railway-vs-cloud-run-measured-2026-11-06)).
- **The Railway account is under the owner's university address,** which ends at graduation. Add a personal login before then, or the account can't be reached.
- **Supabase's free plan pauses a project after a week without activity,** which would break sign-in and saved runs until someone restores it. A scheduled request every day or two keeps it active.
- **GitHub turns off scheduled workflows in a public repository after 60 days without activity,** so S15.5's weekly data refresh would stop. Re-enable it, or move it to the host.
- **The AI assistant (CISC 499)** costs money per use. Keep its caps (S11.6), or turn it off.

## Original decision, 2026-10-23: Fly.io

*Replaced on 2026-11-06 by [Railway](#decision-2026-11-06-railway).*

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

*Replaced on 2026-11-06 by [Railway](#decision-2026-11-06-railway). The Lambda spike won't run.*

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

*Fly.io's trial and costs. Railway's costs are in the [decision](#decision-2026-11-06-railway).*

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

*The Fly.io deployment, which lapsed on 2026-10-31, kept for reference. S15.1 writes Railway's steps.*

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

- [ ] The owner subscribes to Railway's Hobby plan, then sets the hard usage limit to $10 and an email alert at $5.
- [ ] Create the service from this repository with `backend` as its root directory, so Railway builds `backend/Dockerfile`, and turn on deploys from `main`. The image listens on port 8080, so make sure Railway routes to it.
- [ ] Give the store a home: a Railway volume mounted at `/data` (up to 5 GB on Hobby), or a download from a private bucket at startup, which Cloud Run could reuse later. Either way, copy all of `DATA_DIR/store`, including `_versions/`, the data-version manifests (S3.7), so the API serves and echoes the same versions as the machine that ingested. The universe v1 store (S6.5, ingested 2026-10-31, with its XBRL facts added on 2026-11-01 by S5.5) is 8.6 MB.
- [ ] Set `DATA_DIR` and `CORS_ORIGINS`. Keep `SERVE_RAW_PRICES` unset until D2's display rights are settled.
- [ ] For S8.4, run background backtests in a thread in the API process. A redeploy stops the process and any run in it, so at startup, mark runs still `running` as failed.
- [ ] Set `NEXT_PUBLIC_API_URL` on Vercel to the API's URL, and add any preview origins the frontend needs to `CORS_ORIGINS`.
- [ ] Write a smoke test for after each deploy: `/health`, a macro value, a filing, and prices answering 403.
- [ ] Script the store upload, until ingestion runs on a schedule (S15.5).
- [ ] Run the container as a non-root user.
- [ ] With S8.4's real timings, set the service's CPU and memory limits.
- [ ] Once Railway serves the API, remove `backend/fly.toml` and the Fly steps above.
- [ ] Add a personal login to the Railway account, which is under the owner's university address.
- [ ] Optionally, deploy the production image to Cloud Run too, as a free standby for demo days: it costs nothing while idle, and the frontend can point at it if Railway is down. Expect a cold start on its first request.
- [ ] Delete the 2026-11-06 benchmark deployments (Railway project `qtm-bench`, Google Cloud project `qtm-bench-1106-hm6q`) if they're still up.

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

Retrieved 2026-11-06, for the Railway decision:

- **Railway:** the [recovery status page](https://status.railway.com/incident/O1VGXWU5) (sign-ups reopened at 19:19 UTC on 2026-11-02, for paid plans only), the [blog](https://blog.railway.com/) (still only the preliminary report), [cost control](https://docs.railway.com/pricing/cost-control) (a $10 minimum hard limit), and [plans](https://docs.railway.com/pricing/plans).
- **Google Cloud:** [Cloud Run pricing](https://cloud.google.com/run/pricing), [billing settings](https://docs.cloud.google.com/run/docs/configuring/cpu-allocation), [job timeouts](https://docs.cloud.google.com/run/docs/configuring/task-timeout), [Cloud Tasks pricing](https://cloud.google.com/tasks/pricing), and the [free tier](https://cloud.google.com/free).
- **AWS:** [Fargate pricing](https://aws.amazon.com/fargate/pricing/), [Step Functions pricing](https://aws.amazon.com/step-functions/pricing/), [Lambda durable functions](https://aws.amazon.com/about-aws/whats-new/2025/12/lambda-durable-multi-step-applications-ai-workflows/), and a [write-up on inactive container functions](https://dev.classmethod.jp/articles/tsnote-aws-lambda-how-can-i-avoid-the-inactive-state-of-the-lambda-function-en/).
- **Cloudflare:** [Containers pricing](https://developers.cloudflare.com/containers/pricing/), [Containers limits](https://developers.cloudflare.com/containers/platform/limits/), and the [Workers size limit](https://developers.cloudflare.com/changelog/post/2026-09-04-increased-worker-size-limit/).
- **Staying up long term:** [Supabase's free-plan limits](https://www.jetadmin.io/blog/supabase-pricing-2026-guide-to-plans-limits-and-real-world-costs/) and [GitHub on disabled scheduled workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows).

Retrieved 2026-11-06, for the benchmark:

- **Railway:** [plans](https://docs.railway.com/pricing/plans) (Hobby: 48 vCPU, 48 GB and 6 replicas per service), [resource prices](https://docs.railway.com/reference/pricing), [the free trial](https://docs.railway.com/pricing/free-trial) (shared vCPU), [edge limits](https://docs.railway.com/networking/public-networking/specs-and-limits) (15 minutes with data flowing, 5 without), [serverless sleeping](https://docs.railway.com/deployments/serverless), and the incident reports for [February 11](https://blog.railway.com/p/incident-report-february-11-2026), [May 19](https://blog.railway.com/p/incident-report-may-19-2026-gcp-account-outage), [July 2](https://blog.railway.com/p/incident-report-july-2-2026-us-east-services-outage), and [September 30](https://blog.railway.com/p/incident-report-sept-30-2026-routing-disruption).
- **Google Cloud:** [Cloud Run pricing](https://cloud.google.com/run/pricing) (free tier, instance-based and minimum-instance rates, and 100 ms rounding), the [Cloud Billing catalog](https://cloud.google.com/billing/docs/how-to/get-pricing-information-api) for us-east4's egress rate, the [Cloud Run SLA](https://cloud.google.com/run/sla), [billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings), [job task timeouts](https://docs.cloud.google.com/run/docs/configuring/task-timeout) (up to 168 hours), and [Cloud Run instances](https://cloud.google.com/blog/products/serverless/introducing-cloud-run-instances).
