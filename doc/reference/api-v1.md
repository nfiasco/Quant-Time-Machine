# Research API v1: response contract

> **Stories S8.1, S8.2, S4.5, S8.5, and S8.3.** Drafted 2026-10-19 as the contract for S9.1's M2 demo page, and implemented in Sprint 2. Sprint 3 added [`GET /v1/fundamentals/{ticker}`](#get-v1fundamentalsticker) (S5.7, 2026-11-01), then [revision history](#get-v1macroseries_idrevisions) (S4.5), [the catalogs](#get-v1catalogseries) (S8.5), and [the snapshot](#get-v1snapshot) (S8.3) on 2026-11-02. The API's own docs at `/docs` show the examples below, each labeled with the request that produces it. A test replays every one against the test fixtures, so they can't drift. S8.6 will generate TypeScript types from the OpenAPI schema. To change the contract, update this file and the backend in the same pull request, and tell the frontend.

## Conventions

- **Routes** live under `/v1`, return JSON, and use `GET` for every as-of query. Field names are `snake_case`.
- **`as_of` is required** on every data endpoint. There is no default. A default of "now" is exactly the trap FRED's API sets (see the [time model](time-model.md#where-look-ahead-bias-creeps-in)).
- **`as_of` input forms** ([time-model rule 3](time-model.md#3-a-bare-date-means-0930-et-and-a-time-without-an-offset-is-new-york-time), D12):
  - A bare date, such as `2020-06-05`, means 09:30 ET that day.
  - A time without an offset, such as `2020-06-05T08:00`, is New York time. Seconds are optional.
  - A time with an offset or `Z`, such as `2020-06-05T13:30:00Z`, is used as given.
  - A New York time that never happened or happened twice (the daylight-saving hours, such as `2020-03-08T02:30` or `2020-11-01T01:30`) gets a 422. Its message says which offset picks which instant.
- **Timestamps in responses** are ISO 8601 in New York time with the offset, such as `2020-06-05T09:30:00-04:00`.
  - Seconds are always included; fractions only when they aren't zero.
  - The first 16 characters are the ET wall-clock time, so `parseAsOf(knowledge_time.slice(0, 16))` from `frontend/lib/time.ts` turns one into an `EtDateTime`.
- **Dates** (observation periods, sessions, filing dates) are `YYYY-MM-DD`.
- **Tickers** are case-insensitive, and responses return them in uppercase.
  - A ticker is resolved as of the knowledge time (S5.2). For example, `FB` in 2020 is Facebook, because Facebook became `META` in June 2022. Today, `FB` belongs to an unrelated ETF.
  - A ticker that no security in our data used at that time returns 404 `unknown_ticker`.
- **Prices are raw**: as traded, never adjusted for later splits or dividends.

## The envelope

Every successful response has the same four fields:

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": {},
  "reason": null
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `knowledge_time` | string | The exact instant the answer is "as of" |
| `data_version` | string or null | The data version the answer came from: the newest in the store when the request arrived, named by when it was cut, such as `20261101T143005Z` (S3.7). Each finished ingestion run that adds data writes a new one, so answers for a given `data_version` never change. `null` only if the store has none yet. The examples here show the test fixtures' version. |
| `data` | object, array, or null | The answer. When nothing was known yet, it's `null` for single-item endpoints and `[]` for lists. |
| `reason` | string or null | Set when `data` is `null` or `[]`: one sentence the page can show as is. Otherwise `null`. |

"Nothing was known yet" is not an error: it's a 200 with a reason.

Two endpoints are exceptions:

- `GET /v1/knowledge-time?as_of=…` only resolves an `as_of` value, so it returns just the first two fields, with the data version the data endpoints read now:

  ```json
  { "knowledge_time": "2020-06-05T09:30:00-04:00", "data_version": "20261019T120000Z" }
  ```

- [`GET /v1/catalog/signals`](#get-v1catalogsignals) depends on neither time nor data, so it takes no `as_of` and returns `spec_version` and `data`.

## Fields on every record

| Field | Type | Meaning |
| --- | --- | --- |
| `available_at` | string | When the record became public ([time model](time-model.md)) |
| `time_assumed` | boolean | `true` when `available_at` comes from a conservative default rather than a known time (rule 11). Show it as a caveat. |
| `source` | `"alfred"`, `"edgar"`, `"tiingo"`, or `"curated"` | Where the record came from. `"curated"` is one of our own files, such as universe membership, and `source_ref` cites what dates it. |
| `source_ref` | string | A pointer back to the exact source item, such as an accession number or a vintage |

## Endpoints for M2

### `GET /v1/macro/{series_id}`

A series' latest observation as it was published at the knowledge time, or the value of one given period.

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |
| `period` | No | An observation date, written exactly `YYYY-MM-DD`, such as `2020-04-01` for April 2020. Default: the latest period known. |

`GET /v1/macro/UNRATE?as_of=2020-06-05`, after the 08:30 jobs report:

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": {
    "series_id": "UNRATE",
    "title": "Unemployment Rate",
    "units": "Percent",
    "frequency": "Monthly",
    "seasonal_adjustment": "Seasonally Adjusted",
    "release": "Employment Situation",
    "period": "2020-05-01",
    "value": 13.3,
    "vintage_date": "2020-06-05",
    "available_at": "2020-06-05T08:30:00-04:00",
    "time_assumed": false,
    "source": "alfred",
    "source_ref": "UNRATE vintage 2020-06-05"
  },
  "reason": null
}
```

`GET /v1/macro/UNRATE?as_of=2020-06-05T08:00` is half an hour earlier, so the latest value is April's first print:

```json
{
  "knowledge_time": "2020-06-05T08:00:00-04:00",
  "data_version": "20261019T120000Z",
  "data": {
    "series_id": "UNRATE",
    "title": "Unemployment Rate",
    "units": "Percent",
    "frequency": "Monthly",
    "seasonal_adjustment": "Seasonally Adjusted",
    "release": "Employment Situation",
    "period": "2020-04-01",
    "value": 14.7,
    "vintage_date": "2020-05-08",
    "available_at": "2020-05-08T08:30:00-04:00",
    "time_assumed": false,
    "source": "alfred",
    "source_ref": "UNRATE vintage 2020-05-08"
  },
  "reason": null
}
```

`value` can be `null` when the source published the observation as missing (FRED's `.`).

A period that wasn't published yet gives `data: null`. For example, `GET /v1/macro/UNRATE?as_of=2020-06-05&period=2020-06-01` has the reason "No UNRATE value for 2020-06-01 had been published by June 5, 2020, 9:30 AM ET." June's figure came out on July 2.

### `GET /v1/prices/{ticker}`

The latest daily bar whose session had closed by the knowledge time.

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |

`GET /v1/prices/AAPL?as_of=2020-06-05` returns the June 4 bar, because June 5's bar isn't known until 16:00. **The numbers below are made up**, from the test fixtures. Tiingo's terms don't allow sharing its data, so examples and fixtures use synthetic prices. A real `source_ref` looks like `tiingo AAPL 2020-06-04`.

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": {
    "ticker": "AAPL",
    "cik": 320193,
    "session_date": "2020-06-04",
    "open": 102.5,
    "high": 103.5,
    "low": 101.5,
    "close": 102.0,
    "volume": 1300000,
    "available_at": "2020-06-04T16:00:00-04:00",
    "time_assumed": false,
    "source": "tiingo",
    "source_ref": "made up: AAPL 2020-06-04"
  },
  "reason": null
}
```

- `cik` is `null` for securities without one.
- The prices and `volume` can be `null` when the vendor sent none.
- On an early-close day, `available_at` is 13:00 ET.

When no bar is known, as for SPY in our test data, `data` is `null` with a reason such as "Our data has no daily bar for SPY from a session that had closed by June 5, 2020, 9:30 AM ET."

**Display rights.** Until Tiingo display rights are settled (D2), raw prices are off unless the backend setting `SERVE_RAW_PRICES` is `true`. Turn it on only on your own machine. When it's off, this endpoint returns 403 `prices_restricted` before checking any parameter, so the page should show that message rather than a generic error.

### `GET /v1/filings/{ticker}/latest`

The latest filing of one form type that EDGAR had accepted by the knowledge time.

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |
| `form` | No | `10-K`, `10-Q`, or `8-K`, exactly. Default: `10-Q`. `10-K` also covers 10-K405 and 10-KT, and `10-Q` covers 10-QT. |
| `include_amendments` | No | `true` to also count amendments, such as 10-Q/A. Default: `false`. |

`GET /v1/filings/AAPL/latest?as_of=2020-06-05&form=10-Q`:

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": {
    "ticker": "AAPL",
    "cik": 320193,
    "company_name": "Apple Inc.",
    "accession_number": "0000320193-20-000052",
    "form": "10-Q",
    "is_amendment": false,
    "amends": null,
    "period_of_report": "2020-03-28",
    "filing_date": "2020-05-01",
    "available_at": "2020-04-30T18:03:10-04:00",
    "time_assumed": false,
    "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/a10-qq220203282020.htm",
    "index_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/0000320193-20-000052-index.htm",
    "source": "edgar",
    "source_ref": "0000320193-20-000052"
  },
  "reason": null
}
```

- **`available_at` is EDGAR's acceptance time**, corrected for the offset bug in EDGAR's JSON (time-model rule 5).
- **`filing_date` is for display only.** It's the next business day for filings accepted after 5:30 PM ET, as here, so never use it for timing.
- **`amends`** is the accession number of the filing an amendment changes, when it's known, and `null` otherwise.

When nothing was filed yet, `data` is `null`. Facebook went public on May 18, 2012, so on May 21 it hadn't filed a 10-Q. `GET /v1/filings/FB/latest?as_of=2012-05-21` returns:

```json
{
  "knowledge_time": "2012-05-21T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": null,
  "reason": "No 10-Q from Facebook, Inc. had been accepted by EDGAR by May 21, 2012, 9:30 AM ET."
}
```

The company's name is the one it had at the knowledge time.

### `GET /v1/filings/{ticker}`

The filing history up to the knowledge time, newest first.

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |
| `form` | No | `10-K`, `10-Q`, or `8-K`. Default: all three. |
| `include_amendments` | No | Default: `false` |
| `limit` | No | Default `100`, maximum `1000` |

`GET /v1/filings/AAPL?as_of=2020-06-05&form=10-Q&limit=2` returns a list of the same records. The fiscal Q3 10-Q, `0000320193-20-000062`, isn't in it: EDGAR accepted that filing on July 30.

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": [
    {
      "ticker": "AAPL",
      "cik": 320193,
      "company_name": "Apple Inc.",
      "accession_number": "0000320193-20-000052",
      "form": "10-Q",
      "is_amendment": false,
      "amends": null,
      "period_of_report": "2020-03-28",
      "filing_date": "2020-05-01",
      "available_at": "2020-04-30T18:03:10-04:00",
      "time_assumed": false,
      "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/a10-qq220203282020.htm",
      "index_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/0000320193-20-000052-index.htm",
      "source": "edgar",
      "source_ref": "0000320193-20-000052"
    },
    {
      "ticker": "AAPL",
      "cik": 320193,
      "company_name": "Apple Inc.",
      "accession_number": "0000320193-20-000010",
      "form": "10-Q",
      "is_amendment": false,
      "amends": null,
      "period_of_report": "2019-12-28",
      "filing_date": "2020-01-29",
      "available_at": "2020-01-28T18:02:44-05:00",
      "time_assumed": false,
      "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000010/a10-qq1202012282019.htm",
      "index_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000010/0000320193-20-000010-index.htm",
      "source": "edgar",
      "source_ref": "0000320193-20-000010"
    }
  ],
  "reason": null
}
```

A company that filed nothing yet gives `data: []` with a reason. SPY, a fund, files no 10-K, 10-Q, or 8-K, so `GET /v1/filings/SPY?as_of=2020-06-05` gives "No 10-K, 10-Q, or 8-K filings from SPDR S&P 500 ETF Trust had been accepted by EDGAR by June 5, 2020, 9:30 AM ET."

## Endpoints for M3

### `GET /v1/fundamentals/{ticker}`

A company's last quarters of a standard metric, as filed by the knowledge time, oldest first (S5.7).

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |
| `metric` | No | `revenue`, `net_income`, `eps_diluted`, `operating_cash_flow`, `total_assets`, or `shares_outstanding`, exactly. Default: `revenue`. |
| `quarters` | No | How many of the latest quarters, from `1` to `40`. Default: `8`. |

`GET /v1/fundamentals/AAPL?as_of=2020-06-05&metric=revenue&quarters=2`:

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": [
    {
      "ticker": "AAPL",
      "cik": 320193,
      "metric": "revenue",
      "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
      "unit": "USD",
      "period_start": "2019-09-29",
      "period_end": "2019-12-28",
      "fiscal_year": 2020,
      "fiscal_period": "Q1",
      "value": 91819000000.0,
      "derived": false,
      "accession_numbers": ["0000320193-20-000010"],
      "available_at": "2020-01-28T18:02:44-05:00",
      "time_assumed": false,
      "source": "edgar",
      "source_ref": "0000320193-20-000010"
    },
    {
      "ticker": "AAPL",
      "cik": 320193,
      "metric": "revenue",
      "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
      "unit": "USD",
      "period_start": "2019-12-29",
      "period_end": "2020-03-28",
      "fiscal_year": 2020,
      "fiscal_period": "Q2",
      "value": 58313000000.0,
      "derived": false,
      "accession_numbers": ["0000320193-20-000052"],
      "available_at": "2020-04-30T18:03:10-04:00",
      "time_assumed": false,
      "source": "edgar",
      "source_ref": "0000320193-20-000052"
    }
  ],
  "reason": null
}
```

- **Each value is the latest one filed for its quarter** by the knowledge time ([time-model rule 6](time-model.md#6-an-xbrl-fact-is-known-when-the-filing-that-reported-it-was-accepted)). Apple's 10-K and its next year's 10-Q repeat the March quarter's $58,313 million. After each one's acceptance, `accession_numbers` and `available_at` cite it instead.
- **`derived`.** A quarter no filing reported is computed from two year-to-date totals filed by then, and it cites both filings, the longer total's first. Most fourth quarters are like this, because a 10-K reports the full year. `GET /v1/fundamentals/AAPL?as_of=2021-11-01&quarters=2` ends with:

  ```json
  {
    "ticker": "AAPL",
    "cik": 320193,
    "metric": "revenue",
    "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "unit": "USD",
    "period_start": "2021-06-27",
    "period_end": "2021-09-25",
    "fiscal_year": 2021,
    "fiscal_period": "Q4",
    "value": 83360000000.0,
    "derived": true,
    "accession_numbers": ["0000320193-21-000105", "0000320193-21-000065"],
    "available_at": "2021-10-28T18:04:28-04:00",
    "time_assumed": false,
    "source": "edgar",
    "source_ref": "0000320193-21-000105 minus 0000320193-21-000065"
  }
  ```

- **`concept`** is the XBRL concept the value came from. A metric tries its concepts in order for each quarter, so a company whose tag changed keeps one series. Many changed with the 2018 revenue rules (ASC 606).
- **`fiscal_year` and `fiscal_period`** come from the filing that reported the period as its own. For example, Microsoft's quarter from April to June 2021 is fiscal 2021 `Q4`. Both are `null` when no filing in our data reported the period as its own.
- **A quarter without a value is skipped, not filled**, so match quarters by `period_end`, not by position.
- **Instants.** For `total_assets` and `shares_outstanding`, `period_start` is `null`, and the last `quarters` dates come back. Shares outstanding is the count on each filing's cover page, dated shortly before the filing.
- **Nothing filed yet.** `data` is `[]` with a reason. `GET /v1/fundamentals/SPY?as_of=2020-06-05` gives "No filing EDGAR had accepted from SPDR S&P 500 ETF Trust by June 5, 2020, 9:30 AM ET reported quarterly revenue."
- **Errors.** An unknown ticker is a 404, and an unknown metric is a 422.

### `GET /v1/macro/{series_id}/revisions`

Every version of one observation published by the knowledge time, oldest first (S4.5), for the revision viewer (S9.3).

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |
| `period` | Yes | The observation date, written exactly `YYYY-MM-DD`, such as `1990-01-01` for January 1990 |

`GET /v1/macro/UNRATE/revisions?as_of=2020-06-05&period=1990-01-01`:

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": [
    {
      "series_id": "UNRATE",
      "title": "Unemployment Rate",
      "units": "Percent",
      "frequency": "Monthly",
      "seasonal_adjustment": "Seasonally Adjusted",
      "release": "Employment Situation",
      "period": "1990-01-01",
      "value": 5.3,
      "vintage_date": "1990-02-02",
      "available_at": "1990-02-02T08:30:00-05:00",
      "time_assumed": false,
      "source": "alfred",
      "source_ref": "UNRATE vintage 1990-02-02"
    },
    {
      "series_id": "UNRATE",
      "title": "Unemployment Rate",
      "units": "Percent",
      "frequency": "Monthly",
      "seasonal_adjustment": "Seasonally Adjusted",
      "release": "Employment Situation",
      "period": "1990-01-01",
      "value": 5.4,
      "vintage_date": "1996-03-08",
      "available_at": "1996-03-08T08:30:00-05:00",
      "time_assumed": false,
      "source": "alfred",
      "source_ref": "UNRATE vintage 1996-03-08"
    }
  ],
  "reason": null
}
```

- **Each version is a `MacroObservation`**, as in `GET /v1/macro/{series_id}`. `vintage_date` is when it was published, and `available_at` when it became public.
- **Versions published later stay invisible**, as in every read. On June 5, 2020, May 2020's history is its first print alone, 13.3%. The revision to 13.2% came on January 7, 2022.
- **Nothing published yet** gives `data: []` with the same reason as `GET /v1/macro/{series_id}`: "No UNRATE value for 2020-06-01 had been published by June 5, 2020, 9:30 AM ET."
- **Errors.** An unknown series is a 404, and a missing `period` is a 422.

### `GET /v1/catalog/series`

Every series in our catalog, in its order, with how much of it was published by the knowledge time (S8.5).

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |

`GET /v1/catalog/series?as_of=2020-06-05` lists all six series. Here are two:

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": [
    {
      "series_id": "UNRATE",
      "title": "Unemployment Rate",
      "units": "Percent",
      "frequency": "Monthly",
      "seasonal_adjustment": "Seasonally Adjusted",
      "release": "Employment Situation",
      "observations": { "first": "1990-01-01", "last": "2020-05-01" },
      "vintages": { "first": "1990-02-02", "last": "2020-06-05" }
    },
    {
      "series_id": "PAYEMS",
      "title": "All Employees, Total Nonfarm",
      "units": "Thousands of Persons",
      "frequency": "Monthly",
      "seasonal_adjustment": "Seasonally Adjusted",
      "release": "Employment Situation",
      "observations": null,
      "vintages": null
    }
  ],
  "reason": null
}
```

- **`observations`** spans the first and last observation dates published by then. The test data starts UNRATE in 1990; the real store starts it in 1948.
- **`vintages`** spans the dates of the first and last vintages published by then. ALFRED's archive starts later than the data, so an observation is unknown until the first vintage that has it. GDP's first vintage, for example, is December 4, 1991.
- **Both are `null`** for a series with nothing published yet. Every series in the catalog is always listed.

### `GET /v1/catalog/companies`

The members of each universe at the knowledge time, under the tickers and names they used then, with how far each one's data reaches by then (S8.5). For now that's universe v1, `starter_large_caps` (D3).

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |

`GET /v1/catalog/companies?as_of=2020-06-05`, on the test data:

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "cik": 320193,
      "universe": "starter_large_caps",
      "added": "2010-01-01",
      "prices": { "first": "2020-06-01", "last": "2020-06-04" },
      "filings": { "first": "2001-12-21", "last": "2020-04-30" },
      "fundamentals": { "first": "2020-01-28", "last": "2020-04-30" }
    },
    {
      "ticker": "FB",
      "name": "Facebook, Inc.",
      "cik": 1326801,
      "universe": "starter_large_caps",
      "added": "2013-12-23",
      "prices": { "first": "2020-06-04", "last": "2020-06-04" },
      "filings": { "first": "2012-07-31", "last": "2012-07-31" },
      "fundamentals": null
    },
    {
      "ticker": "TWTR",
      "name": "Twitter, Inc.",
      "cik": 1418091,
      "universe": "starter_large_caps",
      "added": "2018-06-07",
      "prices": null,
      "filings": null,
      "fundamentals": null
    }
  ],
  "reason": null
}
```

- **Tickers and names are those at the knowledge time.** Facebook is FB in 2020 and META from June 9, 2022. `ticker` is `null` for a member that had stopped trading but hadn't left yet, such as Twitter from October 28 to November 1, 2022.
- **Membership follows effective dates.** `added` is the first day. Tesla joins on December 21, 2020, and a company drops off the list on the day it leaves.
- **Coverage.** Each range is `null` when nothing is known:
  - `prices`: the sessions of the first and last daily bars;
  - `filings`: the New York dates on which EDGAR accepted the first and last 10-K, 10-Q, or 8-K, or an amendment, across every CIK the company had;
  - `fundamentals`: the same dates for the first and last filings whose XBRL facts we have.
- **Before 2010** the universe is empty, so `data` is `[]` with the reason "No company was in a universe as of June 1, 2009, 9:30 AM ET: membership history starts on 2010-01-01."

### `GET /v1/catalog/signals`

The kinds of signal an experiment spec can use, each with the JSON Schema of its object in a spec's `signals` (S8.5). They depend on neither time nor data, so there's no `as_of`, and the response has no `knowledge_time` or `data_version`. `GET /v1/catalog/signals`, with one schema shortened:

```json
{
  "spec_version": 1,
  "data": [
    {
      "type": "revenue_growth_acceleration",
      "description": "This quarter's year-over-year revenue growth minus last quarter's.",
      "parameters": { "title": "RevenueGrowthAccelerationSignal", "type": "object" }
    },
    {
      "type": "momentum",
      "description": "The total return over a lookback, leaving out the most recent months.",
      "parameters": {
        "additionalProperties": false,
        "description": "The total return over a lookback, leaving out the most recent months.",
        "properties": {
          "type": { "const": "momentum", "title": "Type", "type": "string" },
          "lookback_months": {
            "description": "How many months back the return starts: 12 for 12-1 momentum.",
            "minimum": 1,
            "title": "Lookback Months",
            "type": "integer"
          },
          "skip_months": {
            "description": "How many of the latest months to leave out: 1 for 12-1 momentum. Fewer than\n`lookback_months`.",
            "minimum": 0,
            "title": "Skip Months",
            "type": "integer"
          }
        },
        "required": ["type", "lookback_months", "skip_months"],
        "title": "MomentumSignal",
        "type": "object"
      }
    }
  ]
}
```

- **`parameters`** is the schema that [`experiment-spec-v1.schema.json`](experiment-spec-v1.schema.json) lists under `$defs`, `type` included, so a form can build its fields from it. A test keeps the two equal.
- **The library grows in Sprint 4.** Each signal S7.4 adds to the spec shows up here with no other change.

### `GET /v1/snapshot`

What was known at a moment, and what wasn't yet, for chosen companies and series (S8.3), for S9.2's Time Machine explorer. It reproduces the [June 5, 2020 table](time-model.md#june-5-2020-at-0930-et-1330z), and a test checks every row of it.

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |
| `tickers` | At least one of `tickers` and `series` | Comma-separated, such as `AAPL,TSLA`; up to 10. Each is resolved as of the knowledge time. |
| `series` | At least one of `tickers` and `series` | Comma-separated series IDs, such as `UNRATE,FEDFUNDS`; up to 10 |

- **Entries are trimmed and matched in any case.** A blank entry is dropped, a repeated one counts once, and results keep the order given.
- **Neither list given, or more than 10 entries in one,** is a 422 `invalid_request` naming the parameter: "tickers or series is required." or "tickers can list at most 10."
- **An unknown ticker or series** fails the whole request with 404 `unknown_ticker` or `unknown_series`, naming it, as the single-item endpoints do.

`data` always has two sections, so it's never `null`, and `reason` is always `null`:

| Section | Holds | Rule |
| --- | --- | --- |
| `known` | For each company: the latest daily bar, the latest 10-K, 10-Q, and 8-K, the latest quarter of revenue, and its universes. For each series: the latest observation. | Every record's `available_at` is at or before `knowledge_time`. It's read through `PointInTimeView`, like every other endpoint. |
| `not_yet_known` | For each company: the next bar to close, the next 10-K, 10-Q, and 8-K, later amendments to filings already accepted, later versions of the revenue quarter in `known`, and later universe changes. For each series: the later versions of the observation in `known`. | Every record's `available_at` is after `knowledge_time`, and no later than when the response's data version was cut. It comes from a separate look-ahead module, [`app/data/look_ahead.py`](../../backend/app/data/look_ahead.py), that exists only to teach. A test keeps the backtest engine from importing it, directly or through another module. |

`not_yet_known` shows what a backtest must not see, so never feed it into anything else.

`GET /v1/snapshot?as_of=2020-06-05&tickers=AAPL,TSLA&series=UNRATE,FEDFUNDS`, on the test data and a server with raw prices off. Each record is shortened here: it has every field of its type, and `/docs` shows the whole response.

```jsonc
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "20261019T120000Z",
  "data": {
    "known": {
      "companies": [
        {
          "ticker": "AAPL",
          "cik": 320193,
          "company_name": "Apple Inc.",
          "prices_withheld": true,
          // A PriceBar, as in GET /v1/prices/{ticker}, with its prices withheld.
          "latest_bar": {
            "session_date": "2020-06-04",
            "open": null,
            "high": null,
            "low": null,
            "close": null,
            "volume": null,
            "available_at": "2020-06-04T16:00:00-04:00"
          },
          // Each is a Filing, as in GET /v1/filings/{ticker}/latest, or null. The test
          // data's latest 10-K is from 2001; it skips the years between.
          "latest_filings": {
            "10-K": { "accession_number": "0000912057-01-544436", "form": "10-K405" },
            "10-Q": {
              "accession_number": "0000320193-20-000052",
              "period_of_report": "2020-03-28",
              "available_at": "2020-04-30T18:03:10-04:00"
            },
            "8-K": { "accession_number": "0000320193-20-000050", "available_at": "2020-04-30T16:30:41-04:00" }
          },
          // A Fundamental, as in GET /v1/fundamentals/{ticker}, or null.
          "latest_revenue": {
            "period_end": "2020-03-28",
            "fiscal_period": "Q2",
            "value": 58313000000.0,
            "accession_numbers": ["0000320193-20-000052"],
            "available_at": "2020-04-30T18:03:10-04:00"
          },
          "universes": [
            {
              "universe": "starter_large_caps",
              "added": "2010-01-01",
              "available_at": "2010-01-01T00:00:00-05:00",
              "time_assumed": false,
              "source": "curated",
              "source_ref": "https://www.sec.gov/Archives/edgar/data/884394/000095012309066888/b77788a1nv30d.txt"
            }
          ]
        },
        {
          "ticker": "TSLA",
          "cik": 1318605,
          "company_name": "Tesla, Inc.",
          "prices_withheld": true,
          "latest_bar": null,
          "latest_filings": { "10-K": null, "10-Q": null, "8-K": null },
          "latest_revenue": null,
          "universes": []
        }
      ],
      "series": [
        // Each latest is a MacroObservation, as in GET /v1/macro/{series_id}, or null.
        { "series_id": "UNRATE", "latest": { "period": "2020-05-01", "value": 13.3, "available_at": "2020-06-05T08:30:00-04:00" } },
        { "series_id": "FEDFUNDS", "latest": { "period": "2020-05-01", "value": 0.05, "available_at": "2020-06-01T16:15:00-04:00" } }
      ]
    },
    "not_yet_known": {
      "companies": [
        {
          "ticker": "AAPL",
          "next_bar": { "session_date": "2020-06-05", "available_at": "2020-06-05T16:00:00-04:00" },
          "next_filings": {
            "10-K": { "accession_number": "0000320193-20-000096", "available_at": "2020-10-29T18:06:25-04:00" },
            "10-Q": {
              "accession_number": "0000320193-20-000062",
              "period_of_report": "2020-06-27",
              "available_at": "2020-07-30T19:29:09-04:00"
            },
            "8-K": null
          },
          // A made-up amendment from the test data.
          "later_amendments": [
            {
              "accession_number": "0000320193-20-900001",
              "form": "10-Q/A",
              "amends": "0000320193-20-000052",
              "available_at": "2020-06-10T16:00:00-04:00"
            }
          ],
          "later_revenue": [
            { "value": 58313000000.0, "accession_numbers": ["0000320193-20-000096"], "available_at": "2020-10-29T18:06:25-04:00" },
            { "value": 58313000000.0, "accession_numbers": ["0000320193-21-000056"], "available_at": "2021-04-28T18:02:54-04:00" }
          ],
          "universe_changes": []
        },
        {
          "ticker": "TSLA",
          "next_bar": null,
          "next_filings": { "10-K": null, "10-Q": null, "8-K": null },
          "later_amendments": [],
          "later_revenue": [],
          "universe_changes": [
            {
              "universe": "starter_large_caps",
              "change": "joins",
              "effective": "2020-12-21",
              "available_at": "2020-12-21T00:00:00-05:00",
              "time_assumed": false,
              "source": "curated",
              "source_ref": "https://press.spglobal.com/2020-11-16-Tesla-Set-to-Join-S-P-500"
            }
          ]
        }
      ],
      "series": [
        // Every later version, oldest first, each a MacroObservation.
        { "series_id": "UNRATE", "period": "2020-05-01", "revisions": [{ "value": 13.2, "vintage_date": "2022-01-07", "available_at": "2022-01-07T08:30:00-05:00" }] },
        { "series_id": "FEDFUNDS", "period": "2020-05-01", "revisions": [] }
      ]
    }
  },
  "reason": null
}
```

- **`prices_withheld`** is `true` when the backend's `SERVE_RAW_PRICES` setting is off, as on the deployment (D2). Then `latest_bar` keeps its `session_date` and `available_at`, so the page can still say June 4's close was known, but its prices and `volume` are `null`. Unlike `GET /v1/prices`, the snapshot never answers 403.
- **`latest_bar`** is `null` when no bar from a closed session is in our data. **`next_bar`** is the first bar after the knowledge time, and `null` when our data has none, as after a security's last trading day. It never carries prices: they weren't known yet.
- **`latest_filings` and `next_filings`** always have the keys `10-K`, `10-Q`, and `8-K`, each a `Filing` or `null`. They count original filings only. `next_filings` holds the first of each form accepted after the knowledge time.
- **`later_amendments`** lists amendments, such as a 10-Q/A, that EDGAR accepted after the knowledge time for filings it had accepted by then. Oldest first, up to 10.
- **`latest_revenue`** is the latest quarter of revenue, as `GET /v1/fundamentals/{ticker}?metric=revenue&quarters=1` gives it, or `null`.
- **`later_revenue`** holds each later version of that quarter, oldest first. A new version appears whenever a later filing changed the quarter's value, its concept, or the filings it cites. Each is the quarter as known right after that filing. Apple's March 2020 quarter was re-reported in the fiscal 2020 10-K and in the next year's 10-Q. A restatement shows up the same way, with its new value: a derived fourth quarter is derived again from the restated total.
- **`universes`** lists the company's memberships at the knowledge time. Each has its `universe` and `added`, with `source: "curated"` and the announcement or filing that dates it in `source_ref`.
- **`universe_changes`** lists the company's later joins and leaves, oldest first. Each has `change` (`joins` or `leaves`) and `effective`, its first day. Its `available_at` is 00:00 ET that day, because a change applies from its effective date, never earlier.
- **`series[].latest`** is `null` when nothing had been published yet. Its `not_yet_known` entry then has `period: null` and `revisions: []`.
- **`revisions`** is `[]` when the observation shown was never revised later.
- **"Not yet known" means public after the knowledge time, and by the time the response's `data_version` was cut.** So an answer never changes for a data version, and nothing dated after the cut shows.

## Errors

Every error has the same shape, which replaces FastAPI's default `{"detail": ...}`:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "2:30 AM on March 8, 2020 never happened in New York: clocks jumped from 2:00 to 3:00 AM. Add an offset, or choose another time.",
    "details": [
      { "field": "as_of", "message": "2:30 AM on March 8, 2020 never happened in New York: clocks jumped from 2:00 to 3:00 AM. Add an offset, or choose another time." }
    ]
  }
}
```

| Status | `code` | When |
| --- | --- | --- |
| 404 | `unknown_ticker` | No security in our data used the ticker at the knowledge time |
| 404 | `unknown_series` | The series isn't in our catalog |
| 404 | `not_found` | No endpoint has that path |
| 405 | `method_not_allowed` | The endpoint doesn't accept that method |
| 422 | `invalid_request` | A parameter is missing or invalid, including `as_of` (bad format, or a time that never happened or happened twice). `details` lists each field. |
| 403 | `prices_restricted` | Raw prices are turned off on this deployment (D2) |
| 500 | `internal_error` | A bug. The message is generic and never includes internals. |

- **`message`** is a sentence the page can show as is.
  - An unknown ticker names the moment: "No security in our data used the ticker META as of June 5, 2020, 9:30 AM ET." Facebook traded as FB until June 2022.
  - For several invalid fields, it joins their messages.
- **`details`** is `[]` except for `invalid_request`, where each entry names a parameter, such as `as_of`, `form`, or `limit`.
- **Every error carries the CORS headers**, a 500 included, so the browser can read the body.

## TypeScript types

Until S8.6 generates them from OpenAPI, the frontend can copy these:

```ts
// Use V1Response<Filing | null> for a single item and V1Response<Filing[]> for a list,
// where [] means nothing was known yet.
export type V1Response<T> = {
  knowledge_time: string;
  data_version: string | null; // null only if the backend's store has no data version yet
  data: T;
  reason: string | null;
};

export type KnowledgeTime = {
  knowledge_time: string;
  data_version: string | null;
};

type Provenance = {
  available_at: string;
  time_assumed: boolean;
  source: "alfred" | "edgar" | "tiingo" | "curated";
  source_ref: string;
};

export type MacroObservation = Provenance & {
  series_id: string;
  title: string;
  units: string;
  frequency: string;
  seasonal_adjustment: string;
  release: string;
  period: string;
  value: number | null;
  vintage_date: string;
};

export type PriceBar = Provenance & {
  ticker: string;
  cik: number | null;
  session_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

export type Filing = Provenance & {
  ticker: string;
  cik: number;
  company_name: string;
  accession_number: string;
  form: string;
  is_amendment: boolean;
  amends: string | null;
  period_of_report: string | null;
  filing_date: string;
  document_url: string | null;
  index_url: string;
};

export type Fundamental = Provenance & {
  ticker: string;
  cik: number | null;
  metric: string; // revenue, net_income, eps_diluted, operating_cash_flow, total_assets, or shares_outstanding
  concept: string;
  unit: string;
  period_start: string | null; // null for an instant
  period_end: string;
  fiscal_year: number | null;
  fiscal_period: "Q1" | "Q2" | "Q3" | "Q4" | null;
  value: number;
  derived: boolean;
  accession_numbers: string[];
};

export type DateRange = { first: string; last: string };

export type CatalogSeries = {
  series_id: string;
  title: string;
  units: string;
  frequency: string;
  seasonal_adjustment: string;
  release: string;
  observations: DateRange | null;
  vintages: DateRange | null;
};

export type CatalogCompany = {
  ticker: string | null;
  name: string;
  cik: number | null;
  universe: string;
  added: string;
  prices: DateRange | null;
  filings: DateRange | null;
  fundamentals: DateRange | null;
};

// GET /v1/catalog/signals has no knowledge_time or data_version.
export type SignalCatalog = {
  spec_version: 1;
  data: { type: string; description: string; parameters: Record<string, unknown> }[];
};

type FilingsByForm = { "10-K": Filing | null; "10-Q": Filing | null; "8-K": Filing | null };

export type Membership = Provenance & { universe: string; added: string };

export type UniverseChange = Provenance & {
  universe: string;
  change: "joins" | "leaves";
  effective: string;
};

export type SnapshotCompanyKnown = {
  ticker: string;
  cik: number | null;
  company_name: string;
  prices_withheld: boolean;
  latest_bar: PriceBar | null;
  latest_filings: FilingsByForm;
  latest_revenue: Fundamental | null;
  universes: Membership[];
};

export type SnapshotCompanyNotYetKnown = {
  ticker: string;
  next_bar: { session_date: string; available_at: string } | null;
  next_filings: FilingsByForm;
  later_amendments: Filing[];
  later_revenue: Fundamental[];
  universe_changes: UniverseChange[];
};

export type Snapshot = {
  known: {
    companies: SnapshotCompanyKnown[];
    series: { series_id: string; latest: MacroObservation | null }[];
  };
  not_yet_known: {
    companies: SnapshotCompanyNotYetKnown[];
    series: { series_id: string; period: string | null; revisions: MacroObservation[] }[];
  };
};

// GET /v1/macro/{series_id}/revisions returns V1Response<MacroObservation[]>,
// GET /v1/catalog/series V1Response<CatalogSeries[]>, GET /v1/catalog/companies
// V1Response<CatalogCompany[]>, and GET /v1/snapshot V1Response<Snapshot>.

export type V1Error = {
  error: {
    code:
      | "invalid_request"
      | "unknown_ticker"
      | "unknown_series"
      | "prices_restricted"
      | "not_found"
      | "method_not_allowed"
      | "internal_error";
    message: string;
    details: { field: string; message: string }[];
  };
};
```

With `apiFetch` from `frontend/lib/api/client.ts`, a failed call throws `ApiError`, whose `body` is a `V1Error`.

## Browser access (CORS)

The backend allows requests from the origins in its `CORS_ORIGINS` setting: by default the local dev server (`http://localhost:3000`), plus the Vercel site where it's deployed. Pages can call the API from the browser or from the server, as `getApiHealth` does.

## Coming next

| Endpoint | Story | Sprint |
| --- | --- | --- |
| `POST /v1/backtests`, `GET /v1/backtests/{id}`, `GET /v1/backtests/{id}/audit` | S8.4 | 4 |

`POST /v1/backtests` will take an experiment spec as its body: the model in [`app/backtest/spec.py`](../../backend/app/backtest/spec.py), whose JSON Schema is [`experiment-spec-v1.schema.json`](experiment-spec-v1.schema.json) (S7.1).

A price history and a whole macro series as known at a time (`get_price_history_as_of` and `get_macro_series_as_of`) will get endpoints when a page needs them, using the same envelope.
