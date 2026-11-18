# The canonical backtest, 2010 to 2025

> **Story S7.8.** Run and reviewed 2026-11-15, on data version 20261111T030742Z and engine 1.0.0. The numbers here are that run's. A new data version or engine version gives a new run ID, and this page needs its numbers again.

**The question.** Would buying large US companies whose revenue growth was improving, and whose shares had been rising, have beaten the market from 2010 to 2025, using only what was known at each decision?

**The short answer.** In this run, yes: 18.5% a year against SPY's 13.9%, after costs. But [most of that gap comes from which 50 companies are in the universe](#how-far-to-trust-it), not from the two signals. Holding every member with no signals returns 17.6% a year. The signals add 0.9 points to that, which isn't distinguishable from chance.

## The spec

[`tests/fixtures/specs/canonical.json`](../../backend/tests/fixtures/specs/canonical.json) is the question as an [experiment spec](../reference/experiment-spec-v1.schema.json):

- **Universe:** `starter_large_caps`, [50 curated companies](../reference/data-sources.md#universe-v1-starter_large_caps-decision-d3), each a member while it was in the S&P 500. It had 38 to 41 members at a time.
- **Schedule:** a decision at 09:30 ET on each month's first trading day, filled at that day's close. That's 192 decisions, from January 4, 2010 to December 1, 2025.
- **Signals:** [revenue growth acceleration](../reference/signals.md#3-revenue-growth-acceleration), which is this quarter's year-on-year growth less last quarter's, and [12-1 momentum](../reference/signals.md#1-momentum).
- **Portfolio:** every member with both above zero, at equal weights, long only.
- **Benchmark and costs:** SPY, and 10 bps of the value traded.

## Running it

```bash
cd backend
uv run python -m app.runs tests/fixtures/specs/canonical.json --data-version 20261111T030742Z
```

| | |
| --- | --- |
| Run ID | `ffe49fd67e835e1bf8bcbae09a3d57711e349701e4d466bd045f7e0075018cf3` |
| Spec hash | `6b0fdbf59b2cfae5470d63bafb192461de3b126f674012e08cbf3d2f349d0db1` |
| Data version | 20261111T030742Z |
| Engine | 1.0.0, at commit `f3a971c` |
| Took | 196 seconds, with 336 MB of memory at its peak |
| Saved | 10.9 MB in `DATA_DIR/runs/<run ID>/`, of which `audit.json` is 8.7 MB |

The [run's record](../reference/runs.md) is seven JSON files. Everything below was read from them.

## The result

All after costs, from the first fill, at January 4, 2010's close, to December 31, 2025's:

| Metric | Portfolio | SPY |
| --- | --- | --- |
| Growth of $1 | $15.04 | $8.03 |
| CAGR | 18.5% | 13.9% |
| Volatility, annualized | 16.1% | 15.4% |
| Sharpe ratio | 1.06 | |
| Maximum drawdown, at fills | −22.0% | −23.8% |
| Beta | 0.94 | |
| Alpha, a year | 4.8% | |
| Months ahead of SPY | 107 of 192 (55.7%) | |
| Mean monthly excess return | 0.34%, t-statistic 2.32 | |
| Turnover, a month | 0.61 | |

Both drawdowns are the fall of early 2020, from the February fill (January's for SPY) to April 1's. Costs took 11.7% of the portfolio over the 16 years, about 0.7% a year. The formulas are in the [metrics reference](../reference/metrics.md); SPY's volatility and drawdown aren't in `metrics.json`, and were worked out from the benchmark returns in `returns.json`.

**By year.** Each row is the twelve holding periods decided in that year, so it runs from the January fill's close to the next January's, and SPY's column isn't quite its calendar year.

| Year | Portfolio | SPY | Difference | Holdings, mean (range) |
| --- | --- | --- | --- | --- |
| 2010 | 11.2% | 14.3% | −3.1 | 16.8 (6 to 26) |
| 2011 | 9.7% | 2.5% | +7.2 | 15.6 (8 to 23) |
| 2012 | 17.7% | 17.1% | +0.6 | 7.8 (5 to 12) |
| 2013 | 32.2% | 27.8% | +4.4 | 18.1 (12 to 25) |
| 2014 | 10.6% | 14.5% | −3.9 | 16.2 (12 to 21) |
| 2015 | 3.9% | −0.1% | +4.0 | 12.3 (9 to 19) |
| 2016 | 25.7% | 14.5% | +11.2 | 14.3 (10 to 18) |
| 2017 | 30.3% | 21.6% | +8.7 | 19.9 (14 to 24) |
| 2018 | 5.1% | −5.1% | +10.2 | 19.5 (11 to 26) |
| 2019 | 28.6% | 32.3% | −3.8 | 11.2 (6 to 22) |
| 2020 | 18.7% | 15.7% | +3.0 | 13.6 (6 to 24) |
| 2021 | 26.3% | 31.3% | −5.0 | 24.4 (10 to 31) |
| 2022 | 7.3% | −19.0% | +26.3 | 7.3 (4 to 13) |
| 2023 | 18.8% | 26.0% | −7.2 | 11.5 (4 to 21) |
| 2024 | 31.7% | 25.3% | +6.4 | 15.7 (12 to 20) |
| 2025 | 23.8% | 18.0% | +5.8 | 14.8 (5 to 23) |

- **Ahead in 11 years of 16,** and never down over a year.
- **2022 is the biggest gap,** and the thinnest portfolio. It held ExxonMobil and Marathon Oil in six of its months, and Pioneer in three, while their revenue and shares were both rising and the index fell. In October it held four stocks (AbbVie, ExxonMobil, IBM, and Marathon Oil) and returned 16.6% against SPY's 4.9%, the run's best month.
- **The worst month** was March 2020: −19.6%, against SPY's −19.9%.
- **The portfolio is often concentrated.** It held 4 to 31 stocks, 14.9 on average, and 8 or fewer in 32 months of 192. It never held cash.

## What the engine warned about

The run reported 340 warnings: 337 `missing_signal` and 3 `delisted_exit`. A member without a value for a signal is left out at that decision, and the warning says why.

**Revenue acceleration had no value 312 times,** out of 7,529 member-decisions (4.1%):

| Year | Member-decisions without it | Share |
| --- | --- | --- |
| 2010 | 79 of 456 | 17.3% |
| 2011 | 39 of 456 | 8.6% |
| 2012 | 42 of 456 | 9.2% |
| 2013 | 53 of 465 | 11.4% |
| 2014 | 31 of 456 | 6.8% |
| 2015 | 17 of 465 | 3.7% |
| 2016 to 2018 | 32 of 1,461 | 2.2% |
| 2019 to 2025 | 19 of 3,314 | 0.6% |

- **XBRL's phase-in was thinner than expected, and shorter.** We expected 2010 and 2011 to be thin. At the first decision, 12 of 38 members had no value. By March 2010 it was 6, and by January 2011 it was 3. The largest filers started tagging in mid-2009, and a 10-Q repeats the quarter a year before, so two filings are enough for an acceleration. Abercrombie & Fitch, AMD, and Xilinx, whose first tagged revenue came in August and September 2010, had none until the end of that year.
- **Three companies are 216 of the 312,** and not because of the phase-in. ExxonMobil had none until September 2018 (104 decisions), Pioneer until March 2015 (62), and Goldman Sachs until March 2014 (50). Their filings use a revenue concept the metric doesn't list, or report quarters only later, [as the signal library says](../reference/signals.md#known-limitations). So the run never considered ExxonMobil for its first eight and a half years.
- **The rest are single gaps:** IBM (11, in 2011 to 2013), Discover (13, in 2010 to 2014), Kohl's (6, in 2020), Alphabet (6, around its fourth quarter of 2021), Pfizer (4), Nvidia (3), and one or two each for Citigroup, Cisco, PepsiCo, Microsoft, and Procter & Gamble in the first two months.

**Momentum had no value 25 times,** all for two spin-offs in their first year of trading: AbbVie (13, from January 2013) and PayPal (12, from August 2015). 12-1 momentum needs a close twelve months back. Each also lacked revenue acceleration at first (8 and 3).

**Three holdings stopped trading while held,** each as its acquisition closed. Each was valued at its last close and sold at the next fill, with that part of the portfolio earning nothing in between:

| Holding | Last close | Acquired by | Sold at the fill of |
| --- | --- | --- | --- |
| Celgene | November 20, 2019 | Bristol-Myers Squibb | December 2, 2019 |
| Xilinx | February 11, 2022 | AMD | March 1, 2022 |
| Pioneer Natural Resources | May 2, 2024 | ExxonMobil | June 3, 2024 |

No decision lacked a benchmark return or a risk-free rate, and none left the portfolio empty.

**Update (2026-11-17, S6.7).** Every run now saves these counts in `coverage.json` ([run records](../reference/runs.md#the-coverage-report)). Re-run on engine 1.1.0 and the same data version, the spec gave run `40365a9a…`, whose results are byte for byte the ones above, and whose report has their counts: 326 of 7,529 member-decisions left out for lack of data, 312 without revenue acceleration and 25 without momentum, and the three exits. Valuing the three delisted holdings 30% below their last close (`"delisting": { "assumed_return": -0.3 }`, [portfolio](../reference/portfolio.md#6-delistings)) lowers the CAGR from 18.5% to 18.0%, and $1 becomes $14.10 instead of $15.04.

## Sanity checks

**The benchmark matches published returns.** SPY's total return for each calendar year from 2010 to 2025, worked out from the store, is within 0.005 points of the figure Yahoo Finance lists, in every year: that's the rounding of two decimals. [`test_benchmark_vs_published.py`](../../backend/tests/test_benchmark_vs_published.py) checks it, with `uv run pytest -m local_data`.

| | Here | Published |
| --- | --- | --- |
| 2010 | 15.06% | 15.06% |
| 2013 | 32.31% | 32.31% |
| 2018 | −4.56% | −4.56% |
| 2022 | −18.17% | −18.17% |
| 2025 | 17.72% | 17.72% |
| January 4, 2010 to December 31, 2025 | 702.63% | 702.69% |

The last row compounds the 16 published years and takes off January 4, 2010's return, since the run starts at that day's close. The difference is the published figures' rounding. Each of the run's 192 benchmark returns also equals SPY's daily total returns compounded between the same two closes, to 12 digits.

**The holdings follow the rules.** Across all 2,868 holdings:

- Every one had both signals above zero at its decision.
- Every one was a member of the universe at its decision, and each decision's universe size matches the store's.
- Weights are equal and add up to 1 at every fill.
- Each period's gross return is its holdings' weighted returns, its cost is 10 bps of its turnover, and the net returns compound to the final value.

**The holdings are plausible.** The most held were Apple (101 months of 192), Mastercard (97), Microsoft (96), Amazon (94), Eli Lilly (94), and Home Depot (92). The least held joined late: Lululemon (3), Airbnb (4), CrowdStrike (6).

**Signal values, checked against filings.** At the June 1, 2020 decision the run held ten stocks: AbbVie, Activision Blizzard, Amazon, Eli Lilly, Home Depot, Intel, Johnson & Johnson, Microsoft, PepsiCo, and UnitedHealth.

- **Microsoft was held** with an acceleration of 0.90 points. Its 10-Q accepted April 29, 2020 (`0001564590-20-019706`) reports $35,021 million for the March quarter against $30,571 million a year before, 14.56% more. The quarter before grew 13.66%, $36,906 million against $32,471 million (`0001564590-20-002450`).
- **Apple wasn't,** correctly. Its growth was 0.51% and its acceleration −8.39 points, from the 10-Q accepted April 30 ([`test_apples_revenue_signals_in_the_local_store`](../../backend/tests/test_revenue_growth.py)).
- **The two largest values in the run are real.** Marathon Oil's 333 points in the fall of 2021: $1,143 million in the June quarter against $272 million in 2020's. Citigroup's 238 points in the spring of 2011: $18,371 million in the fourth quarter of 2010 against $5,405 million in 2009's.

**Nothing was read early.** The audit has 385 views that read 2,989,428 rows. On every one, each table's newest row was known at or before the view's time.

**The run is reproducible.** A second run of the whole period, in a fresh process with a different hash seed, gave the same run ID and files that `diff -r` finds no difference in.

## How far to trust it

**Most of the gap is the universe, not the signals.** The same engine, data, schedule, and costs, with one or both filters taken out:

| Portfolio | CAGR | Excess over SPY | Sharpe ratio | Maximum drawdown | Holdings, mean |
| --- | --- | --- | --- | --- | --- |
| Both filters (the canonical spec) | 18.5% | 4.6 | 1.06 | −22.0% | 14.9 |
| Improving revenue growth only | 17.5% | 3.6 | 0.98 | −25.7% | 18.8 |
| Positive momentum only | 17.1% | 3.1 | 1.02 | −23.0% | 29.0 |
| No filters: every member, equal weights | 17.6% | 3.7 | 0.98 | −27.7% | 39.2 |

- **Holding every member already beats SPY by 3.7 points a year,** with a t-statistic of 3.60. That's the universe: 50 large companies chosen in 2026, held at equal weights.
- **The two signals add 0.9 points a year to it.** Month by month, the canonical portfolio beat the unfiltered one by 0.05% on average, a t-statistic of 0.37, and was ahead in 92 months of 192 and 9 years of 16. That's not distinguishable from chance.
- **Either signal alone does slightly worse than no signal.**
- **What the filters did change is the ride:** a lower volatility (16.1% against 16.7%), a shallower drawdown, and a higher Sharpe ratio, for ten times the turnover (0.61 a month against 0.06).
- **2022 cuts both ways.** The canonical portfolio beat the unfiltered one by 20.1 points in 2022, and trailed it by 11.6 in 2021 and 11.2 in 2023.

To run a comparison, take one filter and its signal out of the spec, or both, and run it the same way. These three were run on 2026-11-15 on the same data version, and aren't kept with the canonical run.

**Other things to keep in mind:**

1. **The universe was chosen with hindsight.** It's 50 companies picked in 2026, and it includes Apple, Amazon, Nvidia, and Tesla because they mattered. Including 13 that left reduces survivorship bias but doesn't remove it ([universe v1's limits](../reference/data-sources.md#universe-v1-starter_large_caps-decision-d3)). Universe v2 (S6.6) replaces the hand-picking with a rule.
2. **Equal weights against a cap-weighted index.** SPY is weighted by size. Part of any gap is that difference, and value weights wait for market cap (S6.6).
3. **A t-statistic of 2.32 against SPY isn't proof.** It treats the months as independent, and the unfiltered universe's is higher. Confidence intervals and a placebo test are S14.4's.
4. **The portfolio can be four stocks.** One company's month can decide a year, as in 2022.
5. **Revenue is dated by the 10-Q or 10-K,** not the earnings release that comes first, so the signal sees a quarter a few weeks after the market did.
6. **Costs are 10 bps flat.** There's no spread, market impact, or taxes, and cash earns nothing.
7. **The drawdown is seen only at fills.** A fall within a month that recovers by the next fill isn't in it.

The signal, portfolio, and metrics references list the rest.

## In the demo

This section is the middle of the demo script (S15.4), after the Time Machine and the UNRATE revisions, and before the audit drill-down. It takes about three minutes. The run takes more than three, so show the saved one. Until the results page exists (S9.6), show the command's report and the files.

1. **Ask the question** (20 seconds). "Would buying companies with improving revenue growth and rising shares have beaten the market since 2010? The catch is the same as before: each month, the test may only use what was known that morning."
2. **Show the spec** (30 seconds). The canonical preset in the builder, or `canonical.json`. Point at four things: the universe, the 09:30 decision, the two signals, and the 10 bps. "This document is everything the engine is told. The assistant will write it later; the engine does all the arithmetic."
3. **Show the result** (40 seconds). The report: 192 periods, 18.5% a year against SPY's 13.9%, a Sharpe ratio of 1.06, a drawdown of −22%. "A dollar became $15.04, against $8.03 in the index."
4. **Then take it apart** (50 seconds). The comparison table above. "Before anyone gets excited: holding every company in our universe, with no signals at all, returns 17.6%. The signals add less than a point, and that could be luck. Our 50 companies were picked with hindsight. The tool's job is to make that visible, not to hide it."
5. **Show the warnings** (20 seconds). 340 of them. "ExxonMobil was never considered until 2018, because its filings tag revenue in a way we don't read yet. The run says so, 104 times."
6. **Open one decision** (20 seconds). June 1, 2020: ten holdings. "Microsoft is in, with revenue growth up from 13.7% to 14.6%. Apple is out: its growth had fallen eight points. Which filing said so?" That question opens the audit drill-down: Apple's 10-Q, accepted at 18:03 ET on April 30, is the newest the decision could see.

**Check before the demo:** the run ID above still matches the deployed data version, and `uv run pytest -m local_data` passes.
