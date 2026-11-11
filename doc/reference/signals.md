# Signal library

> **Story S7.4.** Version 1, 2026-11-10. To change a signal, update its code in [`app/backtest/signals/`](../../backend/app/backtest/signals/), its model in [`app/backtest/spec.py`](../../backend/app/backtest/spec.py), its tests, and this page together.

A signal is a number for each stock at each decision. The engine evaluates every signal in a spec through a view bound to the decision's time, so a signal can use only what was known then ([time model](time-model.md)). Filters turn signals into choices: `{"signal": "rev_accel", "op": ">", "value": 0}` holds the stocks whose revenue growth is speeding up.

- **No value, with a reason.** When a signal can't be computed for a stock, it says why. The engine leaves the stock out and records a `missing_signal` warning: "CCC was left out at the 2021-01-04 decision, because rev_accel had no value. No quarterly revenue was known then."
- **Units.** Values are fractions, as returns are: 0.01 is 1%. An absolute macro change is in its series' units instead.
- **Read through the view.** Signals get the decision's `PointInTimeView` and nothing else, and a test checks that nothing in `app/backtest/` reaches the store itself (S7.3). Every row a signal reads is in the view's access log, which a run's audit will come from (S7.7). With no members, as before a universe's history starts, a signal reads nothing.

## The library at a glance

| Type | What it measures | Parameters | Reads | Minimum history |
| --- | --- | --- | --- | --- |
| [`momentum`](#1-momentum) | A total return over whole months, leaving out the latest ones | `lookback_months`, 12 by default, and `skip_months`, 1 by default | Daily bars, splits, and dividends | A close on the window's first and last sessions |
| [`revenue_growth`](#2-revenue-growth) | The latest quarter's revenue over the same quarter a year earlier | `basis`: `"yoy_quarterly"` | Quarterly revenue from 10-Qs and 10-Ks | The latest quarter, no older than 200 days, and the one a year before it |
| [`revenue_growth_acceleration`](#3-revenue-growth-acceleration) | That growth minus the previous quarter's | `basis`: `"yoy_quarterly"` | The same | The latest quarter, the one before it, and the quarter a year before each |
| [`macro_change`](#4-macro-change) | A macro series' change over its latest releases | `series`, `releases`, and `change`: `"absolute"` or `"relative"` | Two observations of the series | The latest observation and the one `releases` periods before it |

## 1. Momentum

```json
{ "type": "momentum", "lookback_months": 12, "skip_months": 1 }
```

Both parameters are optional, so `{ "type": "momentum" }` is 12-1 momentum. The lookback is 1 to 120 months, and the skip less than the lookback. For a decision in month *M*, with a lookback of *L* months and a skip of *S*:

```text
start = the last session before month M − L begins
end   = the last session before month M − S begins

momentum = Π (1 + r_t) − 1, over the sessions t after start, through end
r_t      = k_t × (close_t + div_t) / close_(t−1) − 1
```

- **The terms.** r_t is the session's total return ([time model, rule 4](time-model.md#4-a-daily-price-bar-is-known-at-its-sessions-close)): k_t is the split factor with ex-date *t*, or 1, and div_t the cash dividend per share, or 0. Prices stay as traded.
- **Whole calendar months.** At the June 1, 2020 decision, 12-1 momentum runs from the close on May 31, 2019 to the close on April 30, 2020: the 11 months from June 2019 through April 2020, leaving out May. The window ends before the decision's month begins, so all of it was known at the decision, whatever its time of day, and a later decision in the same month gets the same value.
- **The calendar decides each end.** Both are the last session before a month begins, from the NYSE calendar:

  | Decision | Lookback-skip | `start` | `end` | Why it's a useful case |
  | --- | --- | --- | --- | --- |
  | 2020-06-01 | 12-1 | 2019-05-31 | 2020-04-30 | An ordinary month |
  | 2021-01-04 | 12-1 | 2019-12-31 | 2020-11-30 | January 1 is a holiday |
  | 2020-01-02 | 12-1 | 2018-12-31 | 2019-11-29 | It ends on an early close, the day after Thanksgiving |
  | 2012-11-01 | 1-0 | 2012-09-28 | 2012-10-31 | Markets reopened on October 31, after Hurricane Sandy |
  | 2024-05-01 | 1-0 | 2024-03-28 | 2024-04-30 | It starts before Good Friday, March 29 |

- **Data.** The stock's daily bars, and its splits and dividends, from `start` through `end`, read by its security ID. [`app/backtest/signals/momentum.py`](../../backend/app/backtest/signals/momentum.py) compounds them with `daily_total_returns`, the function the engine values holdings with.
- **Minimum history.** A close on `start` and on `end`: for 12-1 momentum, about 13 months of prices before the decision.

| No value when | Reason |
| --- | --- |
| There's no close on the window's first session, as for a stock whose prices start later | It had no close on 2019-12-31, the start of its 12-1 momentum window. |
| There's no close on its last session | It had no close on 2020-11-30, the end of its 12-1 momentum window. |
| A split or a dividend falls on a day without a close | Its total return from 2019-12-31 to 2020-11-30 couldn't be computed: delta has a corporate action on 2020-08-14 but no close that day. |

## 2. Revenue growth

```json
{ "type": "revenue_growth", "basis": "yoy_quarterly" }
```

```text
g(q) = R(q) / R(q − 4) − 1
```

- **The latest quarter, q.** The quarter with the latest end among those known at the decision. R(q) is its revenue: the latest value filed by then in a 10-Q or a 10-K, or, for a quarter no filing reported, such as a fourth quarter, the difference between two year-to-date totals ([time model, rule 6](time-model.md#6-an-xbrl-fact-is-known-when-the-filing-that-reported-it-was-accepted)). A restatement counts from its own filing's acceptance.
- **A year earlier, q − 4.** The quarter that ended 350 to 380 days before q did, so 52- and 53-week years count: Apple's first quarter of fiscal 2023, 14 weeks long, ended 371 days after its first quarter of fiscal 2022.
- **An example.** At the June 1, 2020 decision, Apple's latest quarter is its fiscal second quarter of 2020, which ended March 28, 2020: $58,313 million, from the 10-Q accepted at 18:03 ET on April 30. The same quarter of 2019 had $58,015 million, so g = 58,313 / 58,015 − 1 = 0.0051, or 0.51%.
- **A derived quarter.** At the November 1, 2021 decision, Apple's latest quarter is its fiscal fourth quarter of 2021, which no filing reported: its 10-K's year minus its first nine months, $83,360 million. That's 28.8% more than a year earlier.
- **Data.** The standard metric `revenue` ([`metrics.toml`](../../backend/app/data/sources/metrics.toml)), read with `PointInTimeView.get_fundamentals_as_of`: up to the last 8 quarters known.
- **Minimum history.** q and q − 4, each with a positive revenue.
- **Recent enough.** q must have ended at most 200 days before the decision. A company that files on time is never that far behind: its slowest report, the 10-K, is due 60 to 90 days after its year ends, or 105 with an extension, so at a monthly decision its latest quarter is at most about 186 days old. An older one means later filings, or their revenue tags, are missing.

| No value when | Reason |
| --- | --- |
| No revenue had been filed, as for a fund such as SPY, before a company's first XBRL filing, or for a concept the metric doesn't list | No quarterly revenue was known then. |
| The latest quarter ended more than 200 days before the decision | Its latest quarter known ended on 2021-03-31, 201 days before: more than 200, so later quarters are missing. |
| The quarter a year earlier isn't known | Revenue for the quarter a year before the one that ended on 2021-03-31 wasn't known. |
| A revenue isn't positive | Revenue for the quarter that ended on 2020-03-31 wasn't positive, so growth isn't defined. |

## 3. Revenue growth acceleration

```json
{ "type": "revenue_growth_acceleration", "basis": "yoy_quarterly" }
```

```text
a(q) = g(q) − g(q − 1)
```

- **The quarter before, q − 1.** The quarter that ended 80 to 119 days before q did, so PepsiCo's 16-week fourth quarters count. Its growth, g(q − 1), compares it with q − 5.
- **Units.** A difference of fractions: 0.02 is 2 percentage points.
- **An example.** At the June 1, 2020 decision, Apple's g(q) is 0.51%. Its fiscal first quarter of 2020, which ended December 28, 2019, had $91,819 million against $84,310 million a year earlier, 8.91%. So a = 0.0051 − 0.0891 = −0.0839: growth slowed by 8.39 points, and the canonical spec's filter, `rev_accel > 0`, leaves Apple out that month. At the November 1, 2021 decision, its derived fourth quarter grew 28.8%, after 36.4% in its third quarter, an acceleration of −7.6 points.
- **Data, and recent enough.** As for revenue growth.
- **Minimum history.** q, q − 1, q − 4, and q − 5, each with a positive revenue.

There's no value for each of the reasons revenue growth gives, for q or for q − 1, and when q − 1 itself isn't known: "Revenue for the quarter before the one that ended on 2021-03-31 wasn't known."

## 4. Macro change

```json
{ "type": "macro_change", "series": "UNRATE", "releases": 3, "change": "absolute" }
```

```text
absolute  x(t) − x(t − k)
relative  x(t) / x(t − k) − 1
```

- **The terms.** x(t) is the latest observation of the series published by the decision, and x(t − k) the observation k = `releases` periods before it: months for a monthly series, quarters for GDP. Each is at its latest version published by then ([time model, rule 7](time-model.md#7-a-macro-observation-is-known-at-its-vintage-date-plus-its-release-time)), so a revision counts from its own release.
- **A release is a new observation.** A vintage that only revises earlier observations, such as PAYEMS's of May 11, 2020, changes their values, but not t.
- **Units.** An absolute change is in the series' units, and a relative one is a fraction: 0.03 is 3%. Use absolute changes for rates: a relative change from a rate near zero, such as TB3MS's 0.01% in late 2011, is huge and unstable.
- **Releases.** 1 to 120 periods.

  | Series | What it is | Every | An absolute change is in |
  | --- | --- | --- | --- |
  | `UNRATE` | The unemployment rate | Month | Percentage points |
  | `PAYEMS` | Nonfarm payrolls | Month | Thousands of jobs |
  | `CPIAUCSL` | The consumer price index | Month | Index points |
  | `GDP` | Gross domestic product | Quarter | Billions of dollars, at an annual rate |
  | `FEDFUNDS` | The effective federal funds rate | Month | Percentage points |
  | `TB3MS` | The 3-month Treasury bill rate | Month | Percentage points |

- **The same for every stock.** So a filter on it holds the portfolio's stocks only while a condition holds. When it doesn't, no stock passes, and the portfolio holds cash, with an `empty_portfolio` warning.
- **An example.** UNRATE over 1 release, on June 5, 2020. At 09:30 ET, May's first print, 13.3%, had come out at 08:30: 13.3 − 14.7 = −1.4 points from April's. At 08:00, before the jobs report, the latest was April's: 14.7 − 4.4 = +10.3 points from March's. Over 2 releases on December 1, 2020, it's June's 11.1% − April's 14.7% = −3.6 points, and on February 1, 2021, after a vintage of January 8 revised April to 14.8%, −3.7.
- **Data.** Two observations: x(t), with `PointInTimeView.get_macro_as_of`, and x(t − k), by its period.
- **Minimum history.** x(t) and x(t − k), each published with a value.

| No value when | Reason |
| --- | --- |
| Nothing was published yet, as before a series' first ALFRED vintage: GDP's of 1991-12-04, and FEDFUNDS's and TB3MS's of 1996-12-03 | No GDP observation had been published by then. |
| The latest observation was published as missing | UNRATE's latest observation, for October 2025, was published as missing. |
| x(t − k) wasn't published | GDP's observation for Q4 1984 hadn't been published by then. |
| x(t − k) was published as missing | UNRATE's observation for October 2025 was published as missing. |
| A relative change starts from a value that isn't positive | FEDFUNDS was 0 for April 2020, so a relative change from it isn't defined. |

## Signals in filters

Every filter compares one signal with a number, and a stock is held only if it passes them all:

```json
"signals": {
  "mom_12_1": { "type": "momentum" },
  "rev_accel": { "type": "revenue_growth_acceleration", "basis": "yoy_quarterly" },
  "unrate_3m": { "type": "macro_change", "series": "UNRATE", "releases": 3, "change": "absolute" },
  "cpi_12m": { "type": "macro_change", "series": "CPIAUCSL", "releases": 12, "change": "relative" }
},
"filters": [
  { "signal": "rev_accel", "op": ">", "value": 0 },
  { "signal": "mom_12_1", "op": ">", "value": 0 },
  { "signal": "unrate_3m", "op": "<", "value": 0 },
  { "signal": "cpi_12m", "op": "<", "value": 0.03 }
]
```

This holds the stocks whose revenue growth is speeding up and whose 12-1 momentum is positive, but only while unemployment is lower than three months before and prices rose less than 3% over the last year.

## Known limitations

1. **Momentum counts whole calendar months.** The days of the decision's own month never count, even for a decision late in the month, and a missing bar on the window's first or last session gives no value rather than a nearby close.
2. **Revenue is dated by the 10-Q or 10-K,** not the earnings release that comes first ([time model, limitation 1](time-model.md#known-limitations-and-open-questions)), so the revenue signals see a quarter a little later than the market did.
3. **Quarters are recognized by their length** ([time model, rule 6](time-model.md#6-an-xbrl-fact-is-known-when-the-filing-that-reported-it-was-accepted)): 80 to 119 days, and year-to-date totals of 161 to 196, 245 to 287, and 350 to 380 days. That covers 13- and 14-week quarters and PepsiCo's 12- and 16-week ones, but a period of another length, such as a transition period after a company changes its fiscal year, is never a quarter.
4. **A derived fourth quarter can mix bases** for a while after a recast ([time model, limitation 4](time-model.md#known-limitations-and-open-questions)).
5. **Coverage.** A company whose filings use a revenue concept the metric doesn't list has no revenue signals until an override in [`metrics.toml`](../../backend/app/data/sources/metrics.toml) adds it. An override can also add concepts up: Discover's income statement has no revenue total, so its revenue is net interest income plus noninterest income. Some gaps remain, listed in [data sources](data-sources.md#sec-xbrl-reported-financials-company-facts): ExxonMobil before 2017 and Pioneer before 2014 have no listed revenue concept, and Goldman Sachs's quarters before 2014 are known only from its 2014 filings on. A few others miss a single fourth quarter, such as Alphabet's for 2021: its 10-K tagged the year `Revenues`, while its 10-Qs tagged the nine months `RevenueFromContractWithCustomerExcludingAssessedTax`, so the quarter can't be derived until the next 10-K repeats the year. Expect more gaps in 2010 and 2011, while XBRL was phasing in.
6. **A 53-week year's 14-week quarter isn't adjusted.** It has a week more than the quarter it's compared with, so its growth runs high, and the next year's growth runs low. Apple's first quarter of fiscal 2023, 14 weeks long, had $117,154 million, 5.5% less than the 13-week quarter a year before, but about 12% less per day. A year later, its 13-week first quarter grew 2.1% on it, about 10% per day. So acceleration swings twice, and PepsiCo's 17-week fourth quarters do the same.
7. **Reads cost time.** Each signal reads each member's data through the view, and the two revenue signals each read every revenue fact a company filed by then. The canonical spec runs 2020 to 2022, 36 decisions, in about 30 seconds, and each decision's access log holds about 18,000 rows.
8. **A missing macro observation blocks every change that ends on it.** BLS never published October 2025's unemployment rate, after the government shutdown, so UNRATE's change has no value while October 2025 is x(t) or x(t − k).

## Named tests

| Test | Signal | Setup | Expected |
| --- | --- | --- | --- |
| `test_12_1_momentum_compounds_total_returns` | `momentum` | Made-up closes with a 2-for-1 split and a 1% dividend in the window | 1.1 × 1.01 × 1.1 − 1, without December's jump |
| `test_momentum_reads_only_its_window` | `momentum` | The same, through a view's access log | Only rows from 2019-12-31 to 2020-11-30 |
| `test_a_future_bar_never_reaches_momentum` | `momentum` | Later versions of a bar and a split in the window, known a microsecond after the decision or in 2099 | The value without them; `test_the_same_rows_count_once_they_are_known` shows they matter |
| `test_growth_is_the_latest_quarter_over_the_same_quarter_a_year_earlier` | `revenue_growth` | Made-up 10-Qs | 120 / 100 − 1 |
| `test_acceleration_is_this_quarters_growth_minus_last_quarters` | `revenue_growth_acceleration` | The same | 20% − 10% |
| `test_a_53_week_year_still_matches_its_quarters` | both | A fiscal calendar like Apple's, with a 14-week quarter | Its quarters match a year and a quarter apart |
| `test_a_16_week_quarter_counts` | both | A fiscal calendar like PepsiCo's, with a 16-week fourth quarter | Growth and acceleration across it |
| `test_a_fourth_quarter_derived_from_the_year_counts` | `revenue_growth` | A 10-K's year and a 10-Q's nine months | Their difference, known from the 10-K's acceptance |
| `test_a_restatement_counts_from_its_own_filing` | `revenue_growth` | A 10-Q/A for the quarter a year earlier | The old value until its acceptance, the restated one after |
| `test_a_future_filing_never_reaches_revenue_signals` | both | The next 10-Q, and a restatement accepted in 2099 | The 10-Q counts from its acceptance, inclusive; the restatement never does |
| `test_a_change_counts_from_the_jobs_report` | `macro_change` | ALFRED's UNRATE vintages, June 5, 2020 | −1.4 points at 09:30 ET, +10.3 at 08:00 |
| `test_each_value_is_its_latest_revision_known_then` | `macro_change` | April 2020's revision of January 8, 2021 | −3.6 points before it, −3.7 after |
| `test_a_release_counts_from_its_time_of_day` | `macro_change` | FEDFUNDS's 16:15 ET release | Unseen at 09:30 that day, seen at 16:15 |
| `test_a_future_release_never_reaches_macro_change` | `macro_change` | A revision and June's first print, published after the decision | −1.4 points; `test_the_same_release_counts_once_it_is_published` shows they matter |
| `test_no_members_means_no_reads` | all | No members | No values, and nothing in the access log |
| `test_apples_revenue_signals_in_the_local_store` (local only) | both | The local store, at the June 1, 2020 and November 1, 2021 decisions | Apple's growth and acceleration from its filings: 0.51% and −8.39 points, then 28.8% and −7.6 points from a derived fourth quarter |
| `test_the_canonical_specs_signals_run_in_the_loop` | `momentum`, `revenue_growth_acceleration` | The canonical spec's signals and filters on a made-up market, January to April 2021 | Hand-checked holdings, values, and `missing_signal` warnings |
