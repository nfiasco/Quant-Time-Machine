# Data sources and terms

> **Story S2.3**, combining spikes S4.1 (ALFRED), S5.1 (EDGAR), and S6.1 (prices). Facts and terms were checked on 2026-10-11; spike results are marked with the date they were retrieved. Terms change, so re-check them before any public launch (S15.7). This is our reading of each provider's terms, not legal advice.

For every source this memo answers:

- what it covers;
- which field tells us when each fact became public;
- the rate limits and the cost;
- what its terms let us do (display it, redistribute it, use it in a public app).

The spike scripts that produced the evidence are in [`backend/spikes/`](../backend/spikes/), and anyone with the keys can re-run them.

## Summary

| Data | Source | When it became public | Limits and cost | Public app? | Status |
| --- | --- | --- | --- | --- | --- |
| Economic series and their revisions | [ALFRED / FRED API](#fred-and-alfred-economic-data-and-its-revisions) | `realtime_start` of each vintage (a date) plus the release's scheduled time | Free key; about 120 requests per minute | Yes, with FRED's notice. None of the six starter series is third-party copyrighted. | Chosen. Verified 2026-10-12 |
| Filing history | [SEC EDGAR submissions API](#sec-edgar-filing-history-submissions-api) | `acceptanceDateTime`, **after a correction** | Free, no key; at most 10 requests per second, with a User-Agent | Yes | Chosen. Verified 2026-10-11 |
| Reported financials | [SEC XBRL company facts API](#sec-xbrl-reported-financials-company-facts) | Acceptance time of the filing (`accn`) that reported each value | Same as above | Yes | Chosen. Verified 2026-10-11 |
| Daily prices, splits, dividends | [Tiingo end-of-day API](#daily-prices-decision-d2) (D2) | The session's close (rule 4 of the [time model](time-model.md)) | Free tier: 50 requests per hour, 1,000 per day, 500 symbols per month | **Not without permission or a license**: free and paid individual plans are internal use only | Chosen. Verified 2026-10-12: raw prices ✓, splits and dividends ✓, delisted companies only partly |
| Survivorship-free reference prices | [WRDS (CRSP) through UD](#wrds-crsp-at-the-university-of-delaware) | Session close; delisting dates and returns | Through UD's subscription | No: internal academic use only | Not requested yet |
| Trading calendar | [`exchange_calendars`](#trading-calendar) | Not applicable | Open source (Apache-2.0) | Yes | Chosen (S3.5) |
| Universe membership | [A curated list, `starter_large_caps`](#universe-v1-starter_large_caps-decision-d3) (D3), dated by S&P's public announcements | The effective date of each change | Free | Yes: we cite public announcements and store only our members' dates | Chosen 2026-10-29 (D3); built 2026-10-31 with 50 members (S6.5), which ingestion loads with SPY |

## FRED and ALFRED (economic data and its revisions)

**What it is.** The St. Louis Fed's API for economic time series. FRED serves the current values. ALFRED is the same API's archive of every earlier version (vintage), queried with real-time parameters. Starter series (S4.2): UNRATE, PAYEMS, CPIAUCSL, GDP, FEDFUNDS, and TB3MS.

**When a value became public.** Each version of an observation carries a *real-time period*, from `realtime_start` to `realtime_end`: the dates during which it was the published value. These are **dates without times**, so we add each release's scheduled time from a release-time table. For example, the BLS Employment Situation comes out at 08:30 ET. See S4.3 and rule 7 of the [time model](time-model.md#7-a-macro-observation-is-known-at-its-vintage-date-plus-its-release-time). For some series, ALFRED's vintage history starts later than the data; values before the first archived vintage count as unknown.

**How to ask "as of".** The endpoints are [`series/observations`](https://fred.stlouisfed.org/docs/api/fred/series_observations.html) and [`series/vintagedates`](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html):

| Goal | Parameters |
| --- | --- |
| What was known on date *D* | `realtime_start=D&realtime_end=D` |
| Every version an observation has had | `realtime_start=1776-07-04&realtime_end=9999-12-31` |
| First releases only | `output_type=4` |
| Specific vintages, side by side | `vintage_dates=D1,D2,…` with `output_type=2` (all observations) or `3` (new and revised only). The output is wide, one column per vintage. |
| The dates when a series changed | `series/vintagedates`, which defaults to all time |

**Trap: the defaults mean "today".** `realtime_start` and `realtime_end` default to today's date. A query without them silently returns *revised* data. Our first research notebook passed `vintage_date=2020-06-01`, which isn't a FRED parameter. FRED ignored it and returned today's values, including May and June 2020 numbers that weren't published until June 5 and July 2, 2020. The notebook is now corrected.

**Missing values** come in two forms:

- **A published value that's missing**, such as the 10-year Treasury yield (DGS10) on January 1, 2020, when markets were closed, comes back as the string `"."`. Parse it as missing, never as zero.
- **An observation that didn't exist yet in a vintage** is simply left out of that vintage's row in JSON `output_type=2` and `3` responses; there's no `"."` placeholder.

**Limits.**

- **Per request:** `series/observations` returns at most 100,000 rows, and `series/vintagedates` at most 10,000. `vintage_dates` takes up to 2,000 dates per JSON request (fewer for some formats and daily series).
- **Request rate:** client libraries and API directories put it at 120 requests per minute per key, with HTTP 429 beyond that. FRED's own terms only say it may impose limits at any time, so we stay well under that and back off on a 429.

**Cost.** Free with an API key. Sign in at [fredaccount.stlouisfed.org](https://fredaccount.stlouisfed.org/apikeys) and request a key. It is 32 lowercase letters and digits, and goes in `FRED_API_KEY` ([setup](../README.md#configuration-and-api-keys)).

**Terms** ([FRED API Terms of Use](https://fred.stlouisfed.org/docs/api/terms_of_use.html)):

- **The required notice.** An app using the API must display, prominently: "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis." It must also tell users that using it means agreeing to FRED's terms, and link to them. The README carries the notice now. The web app's footer and methodology page need it too (S9.1, S9.7).
- **Third-party series.** Some series belong to third parties (their notes say "Copyright"). Anything beyond personal use requires the owner's permission, and FRED can't grant it. The ALFRED spike checked the six starter series: none mentions a copyright. They come from BLS, BEA, and the Federal Reserve Board. Check every new series in S4.6.
- **Other rules.** Don't suggest endorsement, don't use "FRED" or "Federal Reserve Bank" in our hostnames, and publish a privacy policy if the app collects user information. FRED can change limits or end access at any time.

**Spike S4.1 results** ([`spikes/alfred.py`](../backend/spikes/alfred.py), retrieved 2026-10-12):

- **UNRATE's history.** Data starts in January 1948. ALFRED has 800 vintages, from 1960-03-15 to 2026-10-02, each a date with no time. The release is BLS's Employment Situation.
- **January 1990, first print vs. revision:**

  | Value | Real-time period | Meaning |
  | --- | --- | --- |
  | 5.3% | 1990-02-02 to 1996-03-07 | First published; `output_type=4` (initial release) agrees |
  | 5.4% | 1996-03-08 onward | After a later revision |

- **What was known around June 5, 2020.** This is our [time-model](time-model.md) example: May's 13.3% appears exactly on June 5, and FRED's default "today" view returns revised values.

  | Known as of | Mar 2020 | Apr 2020 | May 2020 | Jun 2020 |
  | --- | --- | --- | --- | --- |
  | 2020-06-04 | 4.4 | 14.7 | not yet | not yet |
  | 2020-06-05 | 4.4 | 14.7 | 13.3 | not yet |
  | Today (the API's default) | 4.4 | 14.8 | 13.2 | 11.0 |

- **Several vintages side by side** (`output_type=2`). Each column is one vintage, and "—" means the observation wasn't in that vintage's JSON row:

  | Observation | Vintage 1990-02-02 | 1990-03-09 | 1990-04-06 | 2026-10-02 |
  | --- | --- | --- | --- | --- |
  | December 1989 | 5.3 | 5.3 | 5.3 | 5.4 |
  | January 1990 | 5.3 | 5.3 | 5.3 | 5.4 |
  | February 1990 | — | 5.3 | 5.3 | 5.3 |
  | March 1990 | — | — | 5.2 | 5.2 |

- **Release dates, but no times.** `release/dates` lists the Employment Situation on 2020-05-08, 2020-05-11, 2020-06-05, and 2020-07-02, all without times. So S4.3's release-time table should be built from each series' vintage dates plus BLS's published schedule, not from this list alone.
- **Limits.** No rate-limit headers came back. The per-request limits match the docs (100,000 observations; 10,000 vintage dates).
- **The starter series.** For every one, the vintage history starts years after the data does. Before the first vintage there is no record of what was first published, so those values count as unknown (S4.3). From 1996 on, all six have full vintage history, which covers our 2010–2025 backtests.

  | Series | Release | Data starts | First vintage | Copyright noted |
  | --- | --- | --- | --- | --- |
  | UNRATE | Employment Situation | 1948-01-01 | 1960-03-15 | No |
  | PAYEMS | Employment Situation | 1939-01-01 | 1955-05-06 | No |
  | CPIAUCSL | Consumer Price Index | 1947-01-01 | 1972-07-21 | No |
  | GDP | Gross Domestic Product | 1947-01-01 | 1991-12-04 | No |
  | FEDFUNDS | H.15 Selected Interest Rates | 1954-07-01 | 1996-12-03 | No |
  | TB3MS | H.15 Selected Interest Rates | 1934-01-01 | 1996-12-03 | No |

## SEC EDGAR: filing history (submissions API)

**What it is.** `https://data.sec.gov/submissions/CIK##########.json` (a 10-digit, zero-padded CIK) lists every filing a company has made. Each filing has these fields:

- `accessionNumber`, `form`, `items` (for 8-Ks)
- `filingDate`, `reportDate`, `acceptanceDateTime`
- `primaryDocument`, plus XBRL flags and a few others

The `recent` block holds at least a year of filings, or the latest 1,000 if that's more. Older filings are in extra pages listed under `filings.files`. Results for Apple (CIK 320193), retrieved 2026-10-11:

- 2,265 filings, from 1994-01-26 to 2026-10-08;
- `recent` holds 1,001 of them, back to 2015-09-17;
- one older page holds the rest.

**When a filing became public: `acceptanceDateTime`, corrected.** The three date fields mean different things:

| Field | Meaning | Use it as `available_at`? |
| --- | --- | --- |
| `reportDate` | End of the period the report covers | No: weeks before anyone knew the numbers |
| `filingDate` | Official filing date; the next business day if accepted after 5:30 PM ET | No: a date only, and sometimes a day late |
| `acceptanceDateTime` | When EDGAR accepted the filing | Yes, after the correction below |

**Finding (spike S5.1, retrieved 2026-10-11).** `acceptanceDateTime` ends in "Z", but it is **neither UTC nor Eastern time**: it runs ahead of the true acceptance time by the Eastern UTC offset, 4 hours in EDT and 5 in EST. Two independent checks agree:

1. **EDGAR's own pages.** We compared the JSON with each filing's index page ("Accepted") and its SGML header (`ACCEPTANCE-DATETIME`). Both pages show Eastern wall-clock time.

   | Apple filing | JSON `acceptanceDateTime` | EDGAR "Accepted" (ET) | True UTC |
   | --- | --- | --- | --- |
   | 10-Q, quarter ended 2019-12-28 (winter) | 2020-01-29T04:02:44Z | 2020-01-28 18:02:44 EST | 2020-01-28T23:02:44Z (JSON − 5 h) |
   | 10-Q, quarter ended 2020-03-28 | 2020-05-01T02:03:10Z | 2020-04-30 18:03:10 EDT | 2020-04-30T22:03:10Z (JSON − 4 h) |
   | 10-K, fiscal year ended 2020-09-26 | 2020-10-30T02:06:25Z | 2020-10-29 18:06:25 EDT | 2020-10-29T22:06:25Z (JSON − 4 h) |

2. **The 5:30 PM rule.** Under Regulation S-T Rule 13, a filing accepted after 5:30 PM ET gets the next business day's filing date. We tested which reading of the JSON predicts the actual `filingDate` for all 361 of Apple's 10-K, 10-Q, and 8-K filings:

   | Reading | Filing dates explained |
   | --- | --- |
   | Eastern time labeled Z | 114 of 361 |
   | True UTC | 122 of 361 |
   | **UTC after subtracting the Eastern offset** | **360 of 361** |

   The one exception is an earnings 8-K accepted at 18:55 ET on July 30, 2020 that kept that day's date. The correction holds across every decade of Apple's filings, 1994 through 2026.

**What ingestion (S5.3) must do:** subtract the Eastern UTC offset from the JSON value, or read `ACCEPTANCE-DATETIME` from the SGML header, which is Eastern time. Lock this in with the test `test_edgar_acceptance_time_correction` from the [time model](time-model.md#named-test-cases-for-s36). EDGAR accepts filings only on weekdays, 6 AM to 10 PM ET, and daylight-saving switches happen at 2 AM on Sundays, so the offset is never ambiguous.

**Finding (S5.3, retrieved 2026-10-23): the shift depends on the company's file.** A sample of 36 filings against their index pages:

| Company | Filings checked | JSON minus the index page's "Accepted" |
| --- | --- | --- |
| Apple, Microsoft, JPMorgan, Meta | 30, from 2006 to 2026, morning and evening | +4 h (EDT) or +5 h (EST), every one |
| Twitter | 6, from 2014 to 2022 | 0: true UTC |

Twitter's file has no shift, perhaps because Twitter stopped filing in 2022. Subtracting the offset anyway puts its early-morning 8-Ks at 02:00 to 04:00 ET, when EDGAR is closed, and an evening one on the wrong filing date. So [`sources/edgar.py`](../backend/app/data/sources/edgar.py) checks each company's file. Each filing whose filing date only one reading explains, given EDGAR's hours and the 5:30 PM rule, is a vote. The majority decides, and a file with no votes is treated as shifted. Every file in the starter set is lopsided: Apple 281 to 0, Microsoft 323 to 0, JPMorgan 1,059 to 0, and Meta 191 to 0 for the shift, Twitter 51 to 1 against.

Two more traps:

- **Date-only placeholders.** Many filings from 1994 to 2002 have a time exactly on the hour that corrects to midnight ET: EDGAR kept only the date. There are 228 in the starter set (Apple 51, Microsoft 40, JPMorgan 137).
- **Acceptance after the filing date.** Five JPMorgan 10-K/As from 2004 to 2006 were accepted days after their filing dates.

Ingestion keeps these filings but flags their times as assumed. It uses the end of the filing date in Eastern time, or the acceptance time if that's later (time-model rule 11).

**Limits.**

- **Access policy:** no key, but every request must carry a User-Agent naming who you are and a contact email (SEC's example: "Sample Company Name AdminContact@<sample company domain>.com"). Requests without one get HTTP 403. The maximum is 10 requests per second ([SEC: accessing EDGAR data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)).
- **Freshness:** the JSON updates in real time, typically within a second of dissemination.
- **No browser access:** `data.sec.gov` doesn't support CORS, so the browser can't call it directly. Everything goes through our backend.

**Cost.** Free.

**Terms.** SEC: "Anyone can access and download this information for free." Automated access must follow SEC's fair-access policy: declare a User-Agent, stay at or under the rate limit, and don't crawl the site with bots. Filings are public, so displaying filing metadata and reported numbers is fine. Don't suggest that the SEC endorses us.

## SEC XBRL: reported financials (company facts)

**What it is.** `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` returns every XBRL fact a company has filed. Each fact has these fields:

- the value: `val`
- its period: `start` and `end`
- `fy` and `fp` (fiscal year and period)
- the filing it came from: `form`, `filed`, and `accn`
- sometimes `frame`

XBRL tagging began in 2009 for the largest companies and reached smaller companies by 2011, so earlier fundamentals aren't available this way. Nightly bulk ZIPs (`companyfacts.zip`, `submissions.zip`, published around 3:00 AM ET) cover every company at once (S5.8).

**When a value became public.** `filed` is a date only, so join each fact's `accn` (accession number) to that filing's corrected acceptance time from the submissions API. The same value appears again in every later filing that repeats it, and **each appearance is a separate version** (rule 6 of the [time model](time-model.md#6-an-xbrl-fact-is-known-when-the-filing-that-reported-it-was-accepted)).

Retrieved 2026-10-11: Apple's revenue for the quarter ended March 28, 2020 (`RevenueFromContractWithCustomerExcludingAssessedTax`) appears three times:

| Value | Form | `fy` / `fp` | Accession | Accepted (UTC) | `frame` |
| --- | --- | --- | --- | --- | --- |
| $58,313,000,000 | 10-Q | 2020 / Q2 | 0000320193-20-000052 | 2020-04-30T22:03:10Z | |
| $58,313,000,000 | 10-K | 2020 / FY | 0000320193-20-000096 | 2020-10-29T22:06:25Z | |
| $58,313,000,000 | 10-Q | 2021 / Q2 | 0000320193-21-000056 | 2021-04-28T22:02:54Z | CY2020Q1 |

**Never use the frames API, or the `frame` field, in a backtest.** SEC describes frames as returning one fact per company "that is last filed". The `CY2020Q1` frame for this revenue cites the 2021 10-Q (0000320193-21-000056), not the original 10-Q from 2020 ([SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)). Here the number didn't change. For a restated number, frames would show the restatement as if it had been known all along.

**Limits, cost, and terms:** the same as the submissions API. XBRL data usually updates within a minute of a filing.

## Daily prices (decision D2)

**What we need** (S6.1, FR-D6, NFR-7):

- **Coverage:** daily history back to 2005, including delisted companies (to avoid survivorship bias).
- **Point-in-time data:** **raw** (as-traded) prices with split and dividend events stored separately (adjusted prices leak future splits into the past; see the [time model](time-model.md)).
- **Practicalities:** limits that let us load about 100 tickers, an affordable cost, and terms that let a public app show results.

Spike S6.1 ([`spikes/prices.py`](../backend/spikes/prices.py)) pulls AAPL from 2005, plus three delisted tickers: Lehman Brothers (LEH, which traded as LEHMQ after bankruptcy) and Twitter (TWTR, taken private in 2022). As a raw-or-adjusted check, it reads AAPL's close on 2012-09-19: the raw close was $702.10, and split-adjusted for 2014's 7-for-1 and 2020's 4-for-1 splits it is about $25.08. Results retrieved 2026-10-12; Yahoo and Stooq gave the same results on 2026-10-11.

| | Yahoo Finance (unofficial) | Stooq | Alpha Vantage, free | **Tiingo**, free | WRDS (CRSP) |
| --- | --- | --- | --- | --- | --- |
| History to 2005 | ✓ AAPL from 2005-01-03 (5,283 bars) | Not testable (blocked) | ✗ The free key returns only the latest 100 days (`outputsize=full` is premium) | ✓ AAPL from 2005-01-03 (5,283 bars; Tiingo's data starts 1980-12-12) | ✓ |
| Delisted companies | ✗ LEH, LEHMQ, TWTR: "No data found, symbol may be delisted" | Not testable | Partly: TWTR's last 100 days are there; LEH is an "Invalid API call". `LISTING_STATUS` lists 9,548 delisted symbols, including TWTR but not LEH. | Partly: TWTR ✓ (2013-11-07 to 2022-10-28, 2,260 bars); LEH and LEHMQ are listed but return no prices. Coverage thins out before 2015 (below) | ✓ including delisting returns |
| Raw vs. adjusted | ✗ `close` is **split-adjusted** ($25.08, not $702.10), and so are dividends ($0.094643 for 2012-08-09) | Not testable | Raw closes ✓; adjusted prices and split and dividend events are premium | ✓ Raw `close` ($702.10) plus `adjClose`. Each bar has `divCash`, the dividend as paid ($2.65 for 2012-08-09), and a `splitFactor` | Both, with adjustment factors |
| Limits | Undocumented | API key only through a CAPTCHA, plus a JavaScript bot check | 25 requests per day | 50 per hour, 1,000 per day, 500 symbols per month | Through UD's subscription |
| Cost | Free | Free | Free; premium from $49.99 per month | Free; $30 per month (Power), $50 per month for internal commercial use | Free to Lerner College; $250 per year for other UD users |
| Terms | No automated collection, no commercial reuse, no redistribution without permission | Unclear | Free use is personal and non-commercial; giving others access counts as commercial | **Internal use only**: "you may not display or share the data" | Academic, internal use only; no redistribution |
| Verdict | ✗ Not a source of record | ✗ Not automatable | ✗ No history on the free tier | ✓ **Chosen** | Internal reference only |

**How far back Tiingo's delisted coverage goes.** Tiingo's public ticker list (`supported_tickers.zip`, 108,982 rows) has 15,818 stocks whose data ends before 2025: delisted, merged, or renamed. Counted by the year their data ends:

| Data ends | Before 2005 | 2005–2009 | 2010–2014 | 2015–2019 | 2020–2024 |
| --- | --- | --- | --- | --- | --- |
| Stocks | 2 | 68 | 554 | 5,879 | 9,315 |

Spot checks of companies that disappeared around 2008:

- **Merrill Lynch (MER)** is listed, but only from 2006-12-28 to 2008-12-31.
- **Bear Stearns (BSC) and Countrywide (CFC)** aren't listed.
- **WB** now belongs to Weibo, not Wachovia, a reminder that tickers get reused (S5.2).

Notes on the evidence:

- **Yahoo:** we called its chart endpoint directly with an honest User-Agent. We don't use the `yfinance` library: recent versions impersonate a browser to get past Yahoo's bot checks, which we won't do. Yahoo's [terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) forbid collecting data "using any automated means" without permission and reusing it commercially.
- **Stooq:** the CSV download returned a JavaScript proof-of-work page instead of data. Since early 2026, Stooq reportedly also requires an API key obtained through a CAPTCHA ([pandas-datareader issue](https://github.com/pydata/pandas-datareader/issues/1012)). Getting around either would mean bypassing bot protection, so we stopped there.
- **Alpha Vantage:** limits and premium features are from its [documentation](https://www.alphavantage.co/documentation/) and [premium page](https://www.alphavantage.co/premium/), and the spike confirmed them. Its [terms](https://www.alphavantage.co/terms_of_service/) treat use beyond "private and individual" activity as commercial.
- **Tiingo:**
  - **Docs:** fields and timing are from its [end-of-day docs](https://www.tiingo.com/documentation/end-of-day): "Both raw prices and adjusted prices are available"; most US prices are in by 5:30 PM ET, with corrections until 8 PM. Plans and the internal-use license are from its [pricing page](https://www.tiingo.com/about/pricing).
  - **A quirk:** AAPL's 7-for-1 split in 2014 comes through as a `splitFactor` of 7.000007, not 7. (The spike printed it as 7.00001, rounded to six significant digits; S6.2 found the exact value.)
- **Also considered:**
  - **Alpaca:** a broker whose market-data API has historical stock data only since 2016. Its free Basic plan needs an Alpaca account, uses the IEX feed for real-time data, can't query the latest 15 minutes, and allows 200 calls per minute; data from every exchange costs $99 per month ([Alpaca market data docs](https://docs.alpaca.markets/docs/about-market-data-api)). Bars can be raw or adjusted, but Alpaca says its API data can't be redistributed ([support article, 2022](https://alpaca.markets/support/redistribute-alpaca-api)). Trading, Alpaca's main purpose, is a non-goal (roadmap §1.3). Its history is too short for 2010–2025 backtests, so it isn't chosen.
  - **Nasdaq Data Link:** its free WIKI end-of-day prices stopped updating in 2018, and current US equity datasets are premium.
  - **Paid survivorship-free vendors (for example, Norgate Data):** they cover delisted companies, but we have no budget for them today.

**Decision D2 (decided 2026-10-11, confirmed by the test pull on 2026-10-12):** **Tiingo's end-of-day API is our daily price source.** It is the only candidate that gives, on every bar, the raw close plus the split factor and the dividend actually paid: exactly what we need to compute returns without look-ahead (S6.4). Its free tier comfortably covers a starter universe of about 100 tickers: one request per ticker loads its full history.

What the test pull showed, and what follows:

1. **Raw prices and corporate actions: confirmed.**
   - Store the raw fields and the split and dividend events. Never feed adjusted price levels into signals.
   - In S6.4, round split ratios or allow a small tolerance (AAPL's 2014 split arrives as 7.000007), and reconcile computed returns against `adjClose`.
2. **Delisted companies: only partly covered.**
   - Recent delistings are there: Twitter's data runs to its last trading day. Its final bar, for October 28, 2022, the day the NYSE suspended trading before the open, has zero volume and repeats the previous close. It's a placeholder, not a trade, and delisting exits (S6.7) must treat it that way.
   - Coverage thins out before 2015 and is nearly absent before 2010; Lehman Brothers has no prices.
   - So for universe v1 (D3, S6.5), check each member's Tiingo coverage before including it, and report gaps in every run (S6.7).
   - If WRDS access comes through, use CRSP internally to measure what's missing (R1).
3. **Settle display rights before M5.** Tiingo's free and Power plans are "internal use only". Before the deployed demo shows prices to the public:
   - (a) ask Tiingo whether a non-commercial university project may display charts;
   - (b) or keep raw prices off public pages, show only derived results, and put the demo behind access control (D9);
   - (c) or budget for a redistribution license.

   Until then, the API must not serve raw Tiingo prices to anonymous users.
4. **Keep the fetcher swappable.** S6.2's fetcher should sit behind a small interface, so a licensed or CRSP-based source can replace Tiingo without touching the rest of the system. Done: a new source implements `PriceSource` in [`sources/prices.py`](../backend/app/data/sources/prices.py), as [`sources/tiingo.py`](../backend/app/data/sources/tiingo.py) does.

## WRDS (CRSP) at the University of Delaware

**What UD offers.** UD's WRDS subscription is administered by the Alfred Lerner College of Business and Economics and includes CRSP (historical stock prices and returns, with delisting returns) and Compustat. Lerner College faculty, staff, and students don't pay; other UD users pay $250 a year. Eligible account types include faculty, staff, graduate students, supervised research assistants, and class accounts requested by faculty. The library's business guide says to ask your professor for access. Sources: [UD IT data management page](https://sites.udel.edu/it-rci/services/data-management/) and the [UD Library business data guide](https://guides.lib.udel.edu/business/data), retrieved 2026-10-11.

**What we may do with it.** Use of WRDS is governed by UD's subscription agreement ([WRDS terms of use](https://wrds-www.wharton.upenn.edu/users/tou/)). CRSP's standard terms limit data to internal academic use, with no redistribution or public display. So CRSP can help us:

- validate Tiingo's coverage and our handling of delistings (S6.7);
- back research-only comparison runs.

It can never appear in the public app, in API responses, or in this repository.

**Status: not asked yet.** This is an open action item for the team: email our professor or Lerner IT (contact on the UD page above). Ask:

1. Can CISC 498 students on this project get access, for example through a class or research-assistant account requested by our professor?
2. Does UD's subscription include CRSP's daily stock file with delisting returns?
3. What does the license allow for a student project whose results are shown publicly?

Record the answers here.

## Trading calendar

[`exchange_calendars`](https://github.com/gerrymanoim/exchange_calendars) (version 4.13.2, Apache-2.0 license) provides the NYSE calendar (`XNYS`): sessions, holidays, early closes, and unscheduled closures such as Hurricane Sandy and national days of mourning. It needs no API, has no limits, and its license allows any use. It's used in S3.5.

## Universe membership

Official index membership (for example, the S&P 500's history) is proprietary. S&P Dow Jones Indices licenses it, and public reconstructions are incomplete. Compustat, through UD's WRDS, has historical index constituents, but the same internal-use limits as CRSP apply.

The plan stays as in the roadmap: v1 is a small, documented, curated universe that deliberately includes companies that later left or were delisted (D3, S6.5). Universe v2 is rules-based, the top N by market cap computed from our own data (S6.6).

### Universe v1: `starter_large_caps` (decision D3)

> **Decided 2026-10-29, pending team review.** It follows the roadmap's leaning for D3: a small curated list with documented history. The name is the one the canonical spec uses (roadmap §3.4).

**What it is.** A curated list of 50 to 100 large US companies. v1 aims for 50, the low end of the roadmap's range, and can grow toward 100 once the pipeline handles 50.

**When a company is a member.** From the effective date it joined the S&P 500 until the effective date it left (rule 8 of the [time model](time-model.md#8-universe-membership-applies-from-its-effective-date)). Each date comes from S&P Dow Jones Indices' public announcement of the change, and each one is cited.

- **Stored as** (security, added, removed, source), one row per membership spell. A company that left and later rejoined gets two rows.
- **History starts on 2010-01-01**, the start of the canonical period. A company already in the index then gets `added = 2010-01-01`, citing a source that shows it was a member by that date. Before 2010 the universe is empty, so the engine warns about earlier periods.
- **SPY is the benchmark, not a member.** The [M2 ticker set](#m2-ticker-set) stays as the test set.

**What v1 must include.** It deliberately includes companies that left, so a backtest doesn't see only today's survivors:

- **At least 10 that left between 2010 and 2025:** removed from the index, acquired, taken private, or bankrupt. Twitter, from the M2 set, is one.
- **At least 10 that joined after 2010-01-01**, including Tesla, so rule 8's golden test (`test_universe_change_applies_from_effective_date`) works as written. Meta (Facebook) is another.
- **The rest were members throughout.** Spread them across sectors, with at least two banks, because banks tag revenue differently (S5.6).

**Every member must:**

1. File 10-K and 10-Q reports with the SEC, so XBRL fundamentals exist (S5.5). Foreign companies that file 20-F reports don't qualify.
2. Have Tiingo prices covering its whole membership spell, checked before it's added (R1). Coverage thins out before 2015.
3. Have its ticker and CIK history, with sources, in [`securities.toml`](../backend/app/data/sources/securities.toml) (S5.2).

A company we'd want but can't cover, such as Lehman Brothers, which Tiingo has no prices for, goes in a coverage-gaps table in this section with the reason. It isn't dropped silently, and the methodology page (S9.7) states the gap.

**Why the S&P 500's dates.** Membership was public at the time, because S&P announces each change before it takes effect. The dates can be cited, and rule 8's example works unchanged. We record the announced dates for our members only. This is a curated subset, not a copy of S&P's licensed constituent data or a reconstruction of the index.

**Its limits, for the methodology page.** Choosing which companies to curate still uses hindsight. Including companies that left on purpose reduces survivorship bias but doesn't remove it. Universe v2 (S6.6) replaces hand-picking with a rule computed from our own data.

**The members, built 2026-10-31.** 50 companies:

- 28 were members from 2010 on and never left.
- 13 joined after 2010-01-01, Tesla and Meta among them.
- 13 left: 8 were acquired or taken private, and 5 were removed for size. AMD left in 2013 and rejoined in 2017, so it's one company with two spells.
- The banks are JPMorgan, Bank of America, Wells Fargo, Citigroup, and Goldman Sachs.

Every date is cited in [`universes.toml`](../backend/app/data/sources/universes.toml):

- **S&P's own announcements** date every change after 2010, on its newsroom, press.spglobal.com. A change "after the close" counts from the next session.
- **SPY's annual report** shows membership by 2010-01-01. Its schedule of investments lists every S&P 500 member SPY held on September 30, 2009, and each of these companies is also in its holdings on March 31, 2010.
- **SEC filings** carry each company's identity, in [`securities.toml`](../backend/app/data/sources/securities.toml): its IPO prospectus, or a 2005 filing that names its ticker, plus name changes, new CIKs, and the end of trading.

| Company | Ticker | CIK | Member | Note |
| --- | --- | --- | --- | --- |
| Alphabet Inc. | GOOGL | 1288776, 1652044 | 2010-01-01 on | Was GOOG until 2014; new CIK in 2015 |
| Amazon.com, Inc. | AMZN | 1018724 | 2010-01-01 on |  |
| Apple Inc. | AAPL | 320193 | 2010-01-01 on |  |
| Bank of America Corporation | BAC | 70858 | 2010-01-01 on | Bank |
| Caterpillar Inc. | CAT | 18230 | 2010-01-01 on |  |
| Cisco Systems, Inc. | CSCO | 858877 | 2010-01-01 on |  |
| Citigroup Inc. | C | 831001 | 2010-01-01 on | Bank |
| Eli Lilly and Company | LLY | 59478 | 2010-01-01 on |  |
| ExxonMobil Holdings Corporation | XOM | 34088, 2115436 | 2010-01-01 on | New CIK in 2026 (Texas holding company) |
| Intel Corporation | INTC | 50863 | 2010-01-01 on |  |
| International Business Machines Corporation | IBM | 51143 | 2010-01-01 on |  |
| Johnson & Johnson | JNJ | 200406 | 2010-01-01 on |  |
| JPMorgan Chase & Co. | JPM | 19617 | 2010-01-01 on | Bank |
| Mastercard Incorporated | MA | 1141391 | 2010-01-01 on |  |
| McDonald's Corporation | MCD | 63908 | 2010-01-01 on |  |
| Microsoft Corporation | MSFT | 789019 | 2010-01-01 on |  |
| NVIDIA Corporation | NVDA | 1045810 | 2010-01-01 on |  |
| PepsiCo, Inc. | PEP | 77476 | 2010-01-01 on |  |
| Pfizer Inc. | PFE | 78003 | 2010-01-01 on |  |
| The Boeing Company | BA | 12927 | 2010-01-01 on |  |
| The Coca-Cola Company | KO | 21344 | 2010-01-01 on |  |
| The Goldman Sachs Group, Inc. | GS | 886982 | 2010-01-01 on | Bank |
| The Home Depot, Inc. | HD | 354950 | 2010-01-01 on |  |
| The Procter & Gamble Company | PG | 80424 | 2010-01-01 on |  |
| UnitedHealth Group Incorporated | UNH | 731766 | 2010-01-01 on |  |
| Verizon Communications Inc. | VZ | 732712 | 2010-01-01 on |  |
| Walmart Inc. | WMT | 104169 | 2010-01-01 on | Wal-Mart Stores until 2018 |
| Wells Fargo & Company | WFC | 72971 | 2010-01-01 on | Bank |
| AbbVie Inc. | ABBV | 1551152 | 2013-01-02 on |  |
| Abercrombie & Fitch Co. | ANF | 1018840 | 2010-01-01 to 2013-12-23 | Removed |
| Activision Blizzard, Inc. | ATVI | 718877 | 2015-08-31 to 2023-10-18 | Acquired by Microsoft |
| Advanced Micro Devices, Inc. | AMD | 2488 | 2010-01-01 to 2013-09-23; 2017-03-20 on | Moved to the S&P MidCap 400 in 2013, back in 2017 |
| Airbnb, Inc. | ABNB | 1559720 | 2023-09-18 on |  |
| Celgene Corporation | CELG | 816284 | 2010-01-01 to 2019-11-21 | Acquired by Bristol-Myers Squibb |
| CrowdStrike Holdings, Inc. | CRWD | 1535527 | 2024-06-24 on |  |
| Discover Financial Services | DFS | 1393612 | 2010-01-01 to 2025-05-19 | Acquired by Capital One |
| Etsy, Inc. | ETSY | 1370637 | 2020-09-21 to 2024-09-23 | Removed |
| H&R Block, Inc. | HRB | 12659 | 2010-01-01 to 2020-09-21 | Moved to the S&P MidCap 400 |
| Kohl's Corporation | KSS | 885639 | 2010-01-01 to 2020-09-21 | Moved to the S&P MidCap 400 |
| lululemon athletica inc. | LULU | 1397187 | 2023-10-18 on |  |
| Marathon Oil Corporation | MRO | 101778 | 2010-01-01 to 2024-11-26 | Acquired by ConocoPhillips |
| Meta Platforms, Inc. | META | 1326801 | 2013-12-23 on | Facebook, Inc., as FB until 2022 |
| Palantir Technologies Inc. | PLTR | 1321655 | 2024-09-23 on |  |
| PayPal Holdings, Inc. | PYPL | 1633917 | 2015-07-20 on |  |
| Pioneer Natural Resources Company | PXD | 1038357 | 2010-01-01 to 2024-05-08 | Acquired by Exxon Mobil |
| Tesla, Inc. | TSLA | 1318605 | 2020-12-21 on | Rule 8's golden test |
| Time Warner Inc. | TWX | 1105705 | 2010-01-01 to 2018-06-20 | Acquired by AT&T |
| Twitter, Inc. | TWTR | 1418091 | 2018-06-07 to 2022-11-01 | Taken private |
| Uber Technologies, Inc. | UBER | 1543151 | 2023-12-18 on |  |
| Xilinx, Inc. | XLNX | 743988 | 2010-01-01 to 2022-02-15 | Acquired by AMD |

**Coverage gaps and candidates left out (checked 2026-10-31).** The list takes only companies whose dates and identity can be cited, and whose whole membership Tiingo covers. That means Tiingo's latest listing under the symbol, which is what its API answers with. [`test_universes.py`](../backend/tests/test_universes.py) checks the coverage against Tiingo's public ticker list (`-m network`).

| Candidate | Why it's out |
| --- | --- |
| Monsanto (left 2018-06-07, acquired by Bayer) | Coverage gap: Tiingo's `MON` now answers with Monument Circle Acquisition Corp. (listed 2021–2022), so Monsanto's prices can't be reached by symbol |
| Lehman Brothers, Bear Stearns, Wachovia | Left before 2010, and Tiingo has no prices for the first two |
| Netflix (joined December 2010) | S&P's 2010 announcement isn't online; news reports and Netflix's own 10-K aren't S&P's announcement |
| Visa (joined December 2009) | Not in SPY's holdings on September 30, 2009; S&P's December 2009 announcement wasn't found |
| Abbott Laboratories, Harley-Davidson | No filing from 2004 or 2005 names the ticker (Harley-Davidson's first that does is from October 2006) |
| Macy's, Oracle, Xerox | Their identity changed after 2005: Federated Department Stores became Macy's in 2007, and Oracle (2006) and Xerox (2019) each became a new holding company with a new CIK. Left for a later revision |

**What the first load showed (2026-10-31).** Tiingo had bars for every member, with one missing session in the 22 years loaded: Celgene's on November 21, 2019, the day Nasdaq suspended it.

Like Twitter's, most acquired companies' last bars are placeholders, not trades. They fall on or after the day trading stopped, with little or no volume and the previous close repeated:

- Time Warner on June 15, 2018;
- Celgene on November 22, 2019;
- Xilinx on February 14, 2022;
- Activision Blizzard on October 13, 2023;
- Pioneer on May 3, 2024;
- Marathon Oil on November 22, 2024.

Discover's last bar, May 16, 2025, is a real session. Delisting exits (S6.7) must skip the placeholders.

The list can grow toward 100 members on the same rules.

### M2 ticker set

Ingestion and the walking skeleton (M2) loaded these five companies plus the benchmark until universe v1 was built (S6.5). Each one is there to exercise a specific rule. They stay as the test set: [`tests/fixtures/`](../backend/tests/fixtures/) copies their history, and [`spikes/hosting.py`](../backend/spikes/hosting.py) cycles through them. All five are also universe members. Checked against SEC EDGAR and Tiingo's metadata on 2026-10-19:

| Ticker | Company | CIK | Tiingo prices | Why it's in the set |
| --- | --- | --- | --- | --- |
| AAPL | Apple Inc. | 320193 | 1980-12-12 on | The golden cases in the [time model](time-model.md). Splits in 2014 (7-for-1) and 2020 (4-for-1), dividends since 2012, and a 52/53-week fiscal year ending in late September. |
| MSFT | Microsoft | 789019 | 1986-03-13 on | Its fiscal year ends June 30, which exercises fiscal-quarter logic (S5.7). Regular dividends. |
| JPM | JPMorgan Chase | 19617 | 1983-12-30 on | A bank, whose revenue tags differ from other companies' (S5.6). Its EDGAR history is huge: 26,395 filings in the `recent` block and 71 older pages, mostly structured-note prospectuses. That stress-tests pagination and form filtering (S5.3). |
| META | Meta Platforms (Facebook until June 2022) | 1326801 | 2012-05-18 on, under `META` | The FB → META ticker change (S5.2 overrides). Tiingo files Facebook's whole history under `META`, and Tiingo's `FB` today is an unrelated ETF (listed 2025-06-26). So the price fetcher must look prices up by security, not by the ticker a user typed. |
| TWTR | Twitter, taken private in October 2022 | 1418091 | 2013-11-07 to 2022-10-28 | A delisted company. SEC's current ticker file doesn't list TWTR, and its submissions show no tickers, so it needs an override entry (S5.2). Its last bar later tests delisting exits (S6.7). |
| SPY | SPDR S&P 500 ETF Trust (benchmark) | 884394 | 1993-01-29 on | The default benchmark (S6.2). It files no 10-K or 10-Q, so the filing endpoints should return an empty result with a reason, not an error. |

Loading all six takes six Tiingo requests, against the free plan's 50 per hour and 500 symbols per month. Universe v1 and SPY take 51, so a first load needs two runs an hour apart.

## Known gaps

| Gap | Effect | Mitigation |
| --- | --- | --- |
| **Delisted companies.** Yahoo has none. Tiingo has recent ones (Twitter) but few before 2010 (no Lehman). CRSP has them all, but for internal use only. | Survivorship bias: results look better than reality, especially in the early years | Check each universe member's coverage (S6.5). Include delisted companies the data covers. Report coverage gaps in every run (S6.7, R1). Measure the gap with CRSP if WRDS access comes through. |
| **Historical index membership.** It's proprietary. | Today's index members applied to the past | A curated universe with sources (S6.5, D3); a rules-based universe later (S6.6). |
| **Fundamentals before XBRL** (before 2009 to 2011, depending on company size). | No machine-readable fundamentals for those years | The engine rejects or warns when a spec needs them (§3.4); expect thin data in 2010 and 2011 (R3). |
| **Ticker history.** SEC's ticker file lists only current tickers. | Old or reused tickers resolve to the wrong company | A curated, cited history for the starter universe and reused tickers, in [`securities.toml`](../backend/app/data/sources/securities.toml) (S5.2). A ticker only in SEC's file resolves only from when the file was downloaded. |
| **Release times.** ALFRED has dates, not times. | A release could be visible too early, or too late | A release-time table plus the end-of-day default, flagged (S4.3). |
| **ALFRED vintages start late** for some series. | Early values have no first-release record | Treat values before the first vintage as unknown (S4.3). The spike prints each starter series' first vintage. |
| **EDGAR's acceptance time is shifted** by the Eastern UTC offset in most companies' files, but not all (Twitter's isn't). | Filings would appear 4 to 5 hours late, or early if the shift is removed where there's none | Detect the shift for each company's file and correct it in ingestion, with golden tests (S5.3, S3.6). Placeholder and impossible times fall back to the end of the filing date, flagged. |
| **Corporate actions beyond splits and cash dividends** (spin-offs, mergers, special dividends). | Wrong total returns around those events | Check what Tiingo's `divCash` and `splitFactor` cover in S6.2. Reconcile returns against Tiingo's `adjClose` in S6.4, rounding split ratios such as 7.000007. |

## What the public app may show

| Source | Show in the public app | Offer as downloads or through our API | Condition |
| --- | --- | --- | --- |
| FRED/ALFRED | ✓ | ✓ for government series; third-party copyrighted series need the owner's permission | Show FRED's notice and link its terms |
| SEC EDGAR and XBRL | ✓ | ✓ | Follow fair-access rules when collecting |
| Tiingo (free or Power) | ✗ without permission or a license | ✗ | Internal use only (see D2, step 2) |
| Yahoo | ✗ | ✗ | Not used |
| Alpha Vantage (free) | ✗ | ✗ | Not used |
| WRDS (CRSP, Compustat) | ✗ | ✗ | Internal academic use only; never commit it |
| `exchange_calendars` | ✓ | ✓ | Apache-2.0 |
