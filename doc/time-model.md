# Time model

> **Story S3.1.** Adopted 2026-10-11 as the working rules, pending the team walk-through at sprint review. The default decision and fill timing (D5) is decided. To change a rule, update this file, its golden test (S3.6), and the methodology page (S9.7) together.

Everything in Quant Time Machine answers one question: **what could someone have known at time *T*?** A decision at *T* may use only facts whose `available_at` is at or before *T*. This page defines `available_at` for every kind of data, with a worked example per rule. The examples double as golden test cases.

## Two clocks on every record

Every stored fact has:

- **What it describes:** a date or period. Examples: the June 4 close, Apple's fiscal Q2 2020 revenue, the May 2020 unemployment rate.
- **`available_at`:** when the world could first know it. Examples: 4:00 PM ET for a close, EDGAR's acceptance time for a 10-Q, 8:30 AM ET for the jobs report.
- **`ingested_at`:** when *our* store saved it.

```text
    period end                   available_at                 decision time T
    Mar 28, 2020                 Apr 30, 2020, 18:03 ET       Jun 5, 2020, 09:30 ET
    (Apple's fiscal Q2 ends)     (10-Q accepted by EDGAR)
────┼────────────────────────────┼────────────────────────────┼─────▶ time
    │  not public yet: unusable  │    public: usable (≤ T)    │
```

- **The comparison is inclusive:** a fact with `available_at = T` is visible at *T*.
- **The store is append-only:** a revision, restatement, or re-report is a new row with its own `available_at`, never an overwrite.
- **A saved run pins a data version** (rows with `ingested_at` up to a snapshot), so data added later never changes an old result (S3.7).

## The rules at a glance

| # | Topic | Rule |
| --- | --- | --- |
| 1 | Storage | Timestamps are timezone-aware and stored in UTC |
| 2 | Market clock | `America/New_York` and the NYSE calendar, including holidays, early closes, and unscheduled closures |
| 3 | Knowledge-time input | A bare date means 09:30 ET on that date, and a time without an offset is New York time; every response echoes the exact timestamp it used |
| 4 | Daily price bar | Known at that session's close: 16:00 ET, or 13:00 ET on early-close days |
| 5 | SEC filing | Known at its EDGAR acceptance time, not the period end and not the filing date |
| 6 | XBRL fact | Known at the acceptance time of the filing that reported it; a value re-reported or restated later is a new version from that filing's time |
| 7 | Macro observation | Known at its ALFRED vintage date plus the release's scheduled time; if the time is unknown, assume end of day |
| 8 | Universe membership | A change applies from its effective date, never earlier |
| 9 | Decisions | Default: first trading day of each month at 09:30 ET |
| 10 | Fills | Always strictly after the decision; default: the decision day's close (D5) |
| 11 | Missing or unclear timestamps | Use the later plausible time (conservative) and flag it |

## The rules, with worked examples

### 1. Timestamps are timezone-aware and stored in UTC

Store and compare instants in UTC, and convert to Eastern time only for market dates and display. Inside the system, a naive timestamp (one without a zone) is a bug. Input without an offset gets its zone at the edge, when it's parsed (rule 3). Eastern time is UTC−4 in daylight time (EDT, which in 2020 ran from March 8 to November 1) and UTC−5 in standard time (EST).

| Eastern time | UTC | Why it matters |
| --- | --- | --- |
| 2020-06-05 09:30 EDT | 2020-06-05 13:30Z | The default decision time, in summer |
| 2020-06-05 08:30 EDT | 2020-06-05 12:30Z | The May 2020 jobs report |
| 2020-06-04 16:00 EDT | 2020-06-04 20:00Z | A regular close |
| 2020-11-27 13:00 EST | 2020-11-27 18:00Z | An early close, in winter |
| 1990-02-02 08:30 EST | 1990-02-02 13:30Z | The January 1990 jobs report |

### 2. The market clock is New York time and the NYSE calendar

Trading days, sessions, and closes come from an established calendar library (`exchange_calendars`, exchange `XNYS`; S3.5), never from "weekdays". Examples it must get right:

- the Hurricane Sandy closure (October 29 and 30, 2012)
- the 13:00 ET early close on November 27, 2020
- national days of mourning (December 5, 2018, and January 9, 2025)
- regular holidays such as Good Friday

### 3. A bare date means 09:30 ET, and a time without an offset is New York time

A knowledge time, such as the API's `as_of` parameter, can take three forms:

| Input | Means | UTC |
| --- | --- | --- |
| `2020-06-05` (a bare date) | 09:30 EDT that day | `2020-06-05T13:30Z` |
| `2020-01-15` (a bare date in winter) | 09:30 EST that day | `2020-01-15T14:30Z` |
| `2020-06-05T08:00` (no offset) | 08:00 New York time | `2020-06-05T12:00Z` |
| `2020-06-05T13:30:00Z` or `2020-06-05T09:30:00-04:00` (with an offset) | Used as given | `2020-06-05T13:30Z` |

- **A time without an offset is New York wall-clock time.**
  - The market clock is always New York (rule 2), and that's how people write market times.
  - It's also the form the web app sends (`frontend/lib/time.ts`).
  - Seconds and fractions of a second are optional.
- **A local time that never happened, or happened twice, is rejected.**
  - When clocks spring forward, 02:00–02:59 is skipped, so `2020-03-08T02:30` never happened.
  - When they fall back, 01:00–01:59 happens twice, so `2020-11-01T01:30` is ambiguous.
  - The API returns a 422 error instead of guessing. Add an offset to pick one of the two.
  - These hours are far from market hours, so no real decision is affected.
- **Echo the exact instant.** Every API response includes the knowledge time it actually used, as `knowledge_time`, written in New York time with its offset (`2020-06-05T09:30:00-04:00`). Nobody has to guess. The response format is in [api-v1.md](api-v1.md).
- **No snapping to trading days.** A bare date on a weekend or holiday still means 09:30 ET that day. Knowledge time is just a moment, and data published by then is visible. Trading days matter only for the decision schedule (rule 9).
- **A timestamp without an offset is New York time.** A timestamp with an offset (`Z`, or one such as `-04:00`) is used as given. One without an offset, such as `2020-06-05T09:30`, is read on the market clock like a bare date: 09:30 ET, or 13:30Z. The web app's links use this form. Two hours a year need a rule:
  - **Fall back.** On November 1, 2020, 01:30 happened twice. The later instant (06:30Z) is used, so the system knows less (rule 11).
  - **Spring forward.** On March 8, 2020, 02:30 never happened, so the API returns an error.

  *Changed in Sprint 2. This rule used to reject timestamps without an offset, but the web app already sends them.*

### 4. A daily price bar is known at its session's close

A bar's open, high, low, close, and volume form one record, known at that day's close.

- **A regular day.** AAPL's bar for Thursday, June 4, 2020 has `available_at = 2020-06-04T20:00Z`. At 09:30 ET on June 5, the latest known bar is June 4's. June 5's bar becomes known at `2020-06-05T20:00Z`.
- **An early close.** On Friday, November 27, 2020, the market closed at 13:00 ET, so that day's bar is known at `18:00Z`.
- **Vendor timing isn't market timing.** Vendors publish end-of-day data later; Tiingo says around 17:30 ET, with corrections until 20:00 ET. The close was known to the market at the close, so that's what we use, and a vendor's correction to the same bar isn't a new version.

### 5. An SEC filing is known at its EDGAR acceptance time

The acceptance time is when EDGAR accepted the filing, which is effectively when it became public. Two other dates are tempting and wrong:

- **The period end** is when the quarter ended, weeks before anyone knew the numbers.
- **The filing date** is a date with no time of day. It is also the *next* business day for filings accepted after 5:30 PM ET.

| Apple 10-Q | Accession | Period end | Accepted (ET) | `available_at` (UTC) | Filing date |
| --- | --- | --- | --- | --- | --- |
| Fiscal Q2 2020 | 0000320193-20-000052 | 2020-03-28 | 2020-04-30 18:03:10 | 2020-04-30T22:03:10Z | 2020-05-01 |
| Fiscal Q3 2020 | 0000320193-20-000062 | 2020-06-27 | 2020-07-30 19:29:09 | 2020-07-30T23:29:09Z | 2020-07-31 |

So the fiscal Q2 10-Q is usable from 18:03 ET on April 30 (a 09:30 decision first sees it on May 1). The fiscal Q3 10-Q doesn't exist yet on June 5.

> **Data trap (found in S5.1).** In EDGAR's submissions JSON, `acceptanceDateTime` ends in "Z" but is **neither UTC nor Eastern time**: it runs ahead of the true acceptance time by the Eastern UTC offset. The fiscal Q2 10-Q shows `2020-05-01T02:03:10.000Z`; the true time is `2020-04-30T22:03:10Z`. Ingestion must subtract 4 hours (EDT) or 5 hours (EST), or read `ACCEPTANCE-DATETIME` from the filing's SGML header, which is Eastern time. With that correction, 360 of Apple's 361 10-K, 10-Q, and 8-K filings get exactly the filing date the 5:30 PM rule predicts. See [data-sources.md](data-sources.md#sec-edgar-filing-history-submissions-api).

### 6. An XBRL fact is known when the filing that reported it was accepted

Companies repeat numbers: a quarter's revenue appears in its own 10-Q, often in the next 10-K, and again a year later as a comparative. Each appearance is a separate row whose `available_at` is that filing's acceptance time. For each period, an as-of query takes the most recently filed value at or before *T*.

Apple's revenue for the quarter ended March 28, 2020 (`RevenueFromContractWithCustomerExcludingAssessedTax`) is $58,313 million in three filings:

| Filing | Accession | Accepted (ET) | Visible on June 5, 2020? |
| --- | --- | --- | --- |
| 10-Q, fiscal Q2 2020 | 0000320193-20-000052 | 2020-04-30 18:03:10 | ✓ |
| 10-K, fiscal 2020 | 0000320193-20-000096 | 2020-10-29 18:06:25 | ✗ |
| 10-Q, fiscal Q2 2021 | 0000320193-21-000056 | 2021-04-28 18:02:54 | ✗ |

Here the value never changed. If a later filing had restated it, the restated number would apply only from that filing's acceptance time. **Never use SEC's frames API in a backtest:** it returns one value per company and period, the *last filed* one (for this quarter, the 2021 10-Q).

### 7. A macro observation is known at its vintage date plus its release time

ALFRED records each published version of an observation (a *vintage*) with a `realtime_start` date, but no time of day. We add the release's scheduled time from a release-time table (S4.3); for example, BLS publishes the Employment Situation at 08:30 ET. If a release's time isn't known, we use the end of that day, so it's first usable on the next trading day, and we flag it.

The release-time table lives in [`alfred_series.toml`](../backend/app/data/sources/alfred_series.toml), next to the series that use it. Sources were checked on 2026-10-21:

| Release (FRED ID) | Series | Time (ET) | Source |
| --- | --- | --- | --- |
| Employment Situation (50) | UNRATE, PAYEMS | 08:30 | [BLS schedule](https://www.bls.gov/schedule/news_release/empsit.htm): "08:30 AM" for every release |
| Consumer Price Index (10) | CPIAUCSL | 08:30 | [BLS schedule](https://www.bls.gov/schedule/news_release/cpi.htm): "08:30 AM" for every release |
| Gross Domestic Product (53) | GDP | 08:30 | [BEA schedule](https://www.bea.gov/news/schedule), and BEA's [2023 schedule](https://apps.bea.gov/scb/issues/2022/12-december/1222-news-releases-2023.htm): releases "are posted on www.bea.gov at 8:30 a.m. Eastern time unless otherwise noted" |
| H.15 Selected Interest Rates (18) | FEDFUNDS, TB3MS | 16:15 | [Federal Reserve](https://www.federalreserve.gov/releases/h15/): "The release is posted daily Monday through Friday at 4:15pm." Monthly figures are averages of business days. |

A release that came out at another time on one day gets an exception. The October 1998 Employment Situation was scheduled for 08:30 on Friday, November 6, 1998. Some payroll estimates were posted early by mistake, so BLS released it officially at 1:30 PM EST on Thursday, November 5 ([BLS historical release dates](https://www.bls.gov/bls/histreleasedates.pdf), footnote 2). A vintage dated 1998-11-05 is therefore known at 13:30 EST (18:30Z), not 08:30.

- **May 2020 unemployment.**
  - The first print, 13.3%, came out at 08:30 ET on Friday, June 5, 2020, so `available_at = 2020-06-05T12:30Z`.
  - A 09:30 decision that day sees 13.3%; an 08:00 decision doesn't, and its latest value is April's first print, 14.7%.
  - FRED's value for May 2020 today is a later revision (13.2%) and must never be used for June 2020.
- **January 1990 unemployment.**
  - First published as 5.3% on Friday, February 2, 1990 (08:30 EST = 13:30Z).
  - Revised to 5.4% in the vintage of March 8, 1996, and unchanged since.
  - So any knowledge time from February 2, 1990 through March 7, 1996 sees 5.3%, and from March 8, 1996 on, 5.4%. This was verified with [`spikes/alfred.py`](../backend/spikes/alfred.py).
- **Unknown release time.** A vintage dated 2020-06-01 with no known release time gets `available_at = 2020-06-01 23:59:59.999999 ET`. It's first used by the June 2 09:30 decision and flagged `time_assumed`.
- **Before the first vintage.** ALFRED's archive starts later than the data for every starter series. For example, GDP's first vintage is 1991-12-04, and FEDFUNDS's and TB3MS's is 1996-12-03. Values before a series' first archived vintage count as unknown until that vintage.

### 8. Universe membership applies from its effective date

On November 16, 2020, S&P announced that Tesla would join the S&P 500 before the open on December 21, 2020. In an "S&P 500 members" universe:

- the December 1, 2020 decision excludes TSLA;
- the January 4, 2021 decision includes it.

The announcement was public on November 16, but membership itself starts on the effective date.

### 9. Decisions: the first trading day of each month, at 09:30 ET

| Month | Decision time | Note |
| --- | --- | --- |
| June 2020 | Mon 2020-06-01 09:30 EDT (13:30Z) | |
| July 2020 | Wed 2020-07-01 09:30 EDT (13:30Z) | |
| November 2012 | Thu 2012-11-01 09:30 EDT (13:30Z) | Markets reopened October 31 after Hurricane Sandy |
| January 2021 | Mon 2021-01-04 09:30 EST (14:30Z) | January 1 is a holiday |

### 10. Fills: strictly after the decision; by default, the decision day's close (D5)

A decision at 09:30 ET on Monday, June 1, 2020 sees prices through Friday, May 29's close, and its trades fill at June 1's close (16:00 ET, 20:00Z). On an early-close day, the fill is at 13:00 ET. A decision can never see the bar it trades at.

**D5, decided 2026-10-11.** The default is a 09:30 ET decision with a same-day close fill. The alternative was a fill at the next day's open.

- **Why same-day close:** it keeps the decision and the fill in one session. The 6.5-hour gap is realistic for a monthly strategy. It also matches the experiment spec (`"fill": "same_day_close"`, roadmap §3.4).
- **What stays configurable:** both options satisfy "fill strictly after the decision". The spec keeps the fill setting (S7.2), and the timing stress test (S14.3) compares them.

### 11. Missing or unclear timestamps: use the later plausible time, and flag it

When a time is missing or ambiguous, choose the latest time it could plausibly have been, so the system errs toward knowing *less*, and flag the row so results can show the assumption. Examples:

- a macro release without a known time (rule 7);
- an old EDGAR filing without an acceptance time, which gets the end of its filing date in Eastern time;
- a vintage that predates our release-time table.

## June 5, 2020, at 09:30 ET (13:30Z)

This is the acceptance test for the snapshot endpoint (S8.3) and the Time Machine explorer (S9.2), with each row's exact timestamp.

| Item | `available_at` (UTC) | Known? |
| --- | --- | --- |
| AAPL daily bars through June 4 | 2020-06-04T20:00Z and earlier | ✓ |
| AAPL's June 5 bar | 2020-06-05T20:00Z | ✗ |
| May 2020 unemployment rate, first print 13.3% | 2020-06-05T12:30Z | ✓ |
| Later revisions to May 2020 (for example, today's 13.2%) | Later vintages | ✗ |
| Apple's 10-Q for the quarter ended March 28, 2020 | 2020-04-30T22:03:10Z | ✓ |
| Apple's fiscal Q2 2020 revenue, $58,313 million, from that 10-Q | 2020-04-30T22:03:10Z | ✓ |
| The same revenue as re-reported in the fiscal 2020 10-K | 2020-10-29T22:06:25Z | ✗ |
| Apple's 10-Q for the quarter ended June 27, 2020 | 2020-07-30T23:29:09Z | ✗ |
| Any 10-Q/A or 10-K/A filed after June 5 | Its own acceptance time | ✗ |
| Fed and other economic data as published by that morning | The latest vintage at or before *T* | ✓ |
| Universe changes effective after June 5 | Their effective dates | ✗ |

## Where look-ahead bias creeps in

The pitfalls table in [roadmap §2.4](roadmap.md#24-where-look-ahead-bias-creeps-in) lists the traps these rules close. Two more turned up in Sprint 1:

- **Timestamps that lie about their zone.** EDGAR's JSON acceptance times (rule 5).
- **API defaults that mean "today".** FRED's `realtime_start` and `realtime_end` default to today, so a query without them returns revised data. Our research notebook fell into exactly this: it passed a `vintage_date` parameter, which FRED ignores, and silently got today's values.

## Known limitations and open questions

1. **Earnings releases come first, so our rule is conservative.** Companies announce results in an 8-K press release before the 10-Q. Apple's 8-K for fiscal Q2 2020 was accepted at 16:30:41 ET on April 30, 2020, and the 10-Q at 18:03:10 ET. For other companies the gap can be days. We date fundamentals by the filing their XBRL numbers come from, so they become usable slightly later than in reality. That's acceptable for v1; say so on the methodology page.
2. **A decision at exactly 16:00.** The bar is known at 16:00 (the comparison is inclusive), so a 16:00 decision can use that close. But fills must be strictly after the decision, so its earliest fill is the next session. A same-day close fill is allowed only for decisions before the close.
3. **Release times are today's schedules.** ALFRED has dates only, so the release-time table (rule 7) supplies the time of day, with two limits:
   - **The times are applied to every vintage.** BLS's 08:30 is documented back to 1998 by its own footnote, and the January 1990 example above assumes it. BEA's and the Fed's times are documented only for recent years.
   - **Not every vintage date is a scheduled release.** A vintage dated on another day, such as a FRED correction, still gets its release's time, unless it's listed as an exception. For example, PAYEMS has a vintage dated Monday, May 11, 2020, three days after the April 2020 jobs report, that changed three observations (April from 131,072 to 131,045 thousand). It counts as known at 08:30 that day.

   A release without a time in the table uses the end-of-day rule and is flagged.
4. **Ticker history.** SEC's ticker file lists only current tickers, so ticker history comes from a curated file, [`securities.toml`](../backend/app/data/sources/securities.toml) (S5.2).
   - It covers the starter set plus tickers that changed hands: FB became META, GOOG moved from Google's Class A to its Class C shares, and WB went from Wachovia to Weibo. Each change cites its source.
   - A ticker that only SEC's file lists is known only from when that file was downloaded, so it can't be used for earlier dates.

## Named test cases for S3.6

Each rule becomes at least one golden test, built on small committed fixtures (no network, no keys).

| Test | Rule | Setup | Expected |
| --- | --- | --- | --- |
| `test_timestamps_are_timezone_aware_utc` | 1 | Load any fixture row | Every `available_at` and `ingested_at` is aware and in UTC |
| `test_calendar_closures_and_early_closes` | 2 | Calendar for 2012-10-29/30, 2018-12-05, 2020-11-27 | Closed, closed, early close at 13:00 ET |
| `test_bare_date_means_0930_eastern` | 3 | Parse `2020-06-05` and `2020-01-15` | `13:30Z` and `14:30Z`, echoed in the response |
| `test_no_offset_timestamp_means_eastern` | 3 | Parse `2020-06-05T09:30` | `13:30Z`, the same as the bare date |
| `test_no_offset_timestamp_in_dst_change_hours` | 3, 11 | Parse `2020-11-01T01:30` and `2020-03-08T02:30` | `06:30Z`, the later of the two instants; a validation error |
| `test_bar_known_only_after_close` | 4 | AAPL bars, *T* = 2020-06-05 09:30 ET | Latest bar is June 4; June 5 raises `LookAheadError` |
| `test_early_close_bar_known_at_1300` | 4 | Bar for 2020-11-27 | `available_at` = 18:00Z |
| `test_filing_known_from_acceptance_time` | 5 | Apple filings, *T* = 2020-06-05 09:30 ET | Latest 10-Q is 0000320193-20-000052; -20-000062 is invisible |
| `test_filing_visible_after_acceptance_not_filing_date` | 5 | *T* = 2020-04-30 18:05 ET | The fiscal Q2 10-Q is already visible (its filing date is May 1) |
| `test_edgar_acceptance_time_correction` | 5 | JSON `2020-05-01T02:03:10.000Z` and `2020-01-29T04:02:44.000Z` | `2020-04-30T22:03:10Z` and `2020-01-28T23:02:44Z` |
| `test_fact_versions_follow_filing_acceptance` | 6 | The three filings of Apple's fiscal Q2 2020 revenue | June 5, 2020 sees only the 10-Q row |
| `test_restatement_applies_from_amendment` | 6 | A synthetic restated value in a later 10-K/A | The old value before the amendment's acceptance, the new one after |
| `test_macro_first_print_vs_revision_jan_1990` | 7 | UNRATE vintages | 5.3% from 1990-02-02 08:30 ET through 1996-03-07; 5.4% from 1996-03-08 on |
| `test_may_2020_unrate_known_at_0930_not_0800` | 7 | UNRATE vintages | 09:30 ET on 2020-06-05 sees 13.3%; 08:00 ET sees April's 14.7% as the latest |
| `test_unknown_release_time_is_end_of_day_and_flagged` | 7, 11 | A vintage with no release time | `available_at` is 23:59:59.999999 ET that day; flagged |
| `test_universe_change_applies_from_effective_date` | 8 | TSLA added effective 2020-12-21 | Not a member on 2020-12-01; a member on 2021-01-04 |
| `test_first_trading_day_of_month` | 9 | 2020-06, 2020-07, 2012-11, 2021-01 | June 1, July 1, November 1, January 4 at 09:30 ET |
| `test_fill_strictly_after_decision` | 10 | Decision 2020-06-01 09:30 ET | Fill at 2020-06-01 16:00 ET; signals see bars through May 29 only |
| `test_poisoned_future_row_never_returned` | All | Add a row with `available_at` in 2099 | It never appears in any query result (S3.3) |
| `test_pinned_data_version_ignores_later_rows` | Two clocks | Pin a data version, then ingest more rows | The pinned query's result doesn't change (S3.7) |
