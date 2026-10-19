# Research API v1: response contract

> **Stories S8.1 and S8.2.** Drafted 2026-10-19 as the contract for S9.1's M2 demo page, pending the frontend's review. The backend implements it in Sprint 2. Until then, build against the examples below. Once the API is live, its OpenAPI docs at `/docs` are the reference, and S8.6 generates TypeScript types from them. To change the contract, update this file and the backend in the same pull request, and tell the frontend.

## Conventions

- **Routes** live under `/v1`, return JSON, and use `GET` for every as-of query. Field names are `snake_case`.
- **`as_of` is required** on every data endpoint. There is no default. A default of "now" is exactly the trap FRED's API sets (see the [time model](time-model.md#where-look-ahead-bias-creeps-in)).
- **`as_of` input forms** ([time-model rule 3](time-model.md#3-a-bare-date-means-0930-et-and-a-time-without-an-offset-is-new-york-time), D12):
  - A bare date, such as `2020-06-05`, means 09:30 ET that day.
  - A time without an offset, such as `2020-06-05T08:00`, is New York time. Seconds are optional.
  - A time with an offset or `Z`, such as `2020-06-05T13:30:00Z`, is used as given.
  - A New York time that never happened or happened twice (the daylight-saving hours, such as `2020-03-08T02:30` or `2020-11-01T01:30`) gets a 422.
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
  "data_version": null,
  "data": {},
  "reason": null
}
```

| Field | Type | Meaning |
| --- | --- | --- |
| `knowledge_time` | string | The exact instant the answer is "as of" |
| `data_version` | string or null | The data version the answer came from. `null` until data versions exist (S3.7, Sprint 3), then always a string. |
| `data` | object, array, or null | The answer. When nothing was known yet, it's `null` for single-item endpoints and `[]` for lists. |
| `reason` | string or null | Set when `data` is `null` or `[]`: one sentence the page can show as is. Otherwise `null`. |

"Nothing was known yet" is not an error: it's a 200 with a reason.

## Fields on every record

| Field | Type | Meaning |
| --- | --- | --- |
| `available_at` | string | When the record became public ([time model](time-model.md)) |
| `time_assumed` | boolean | `true` when `available_at` comes from a conservative default rather than a known time (rule 11). Show it as a caveat. |
| `source` | `"alfred"`, `"edgar"`, or `"tiingo"` | Where the record came from |
| `source_ref` | string | A pointer back to the exact source item, such as an accession number or a vintage |

## Endpoints for M2

### `GET /v1/macro/{series_id}`

A series' latest observation as it was published at the knowledge time, or the value of one given period.

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |
| `period` | No | An observation date (`YYYY-MM-DD`, such as `2020-04-01` for April 2020). Default: the latest period known. |

`GET /v1/macro/UNRATE?as_of=2020-06-05`, after the 08:30 jobs report:

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": null,
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
  "data_version": null,
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

### `GET /v1/prices/{ticker}`

The latest daily bar whose session had closed by the knowledge time.

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |

`GET /v1/prices/AAPL?as_of=2020-06-05` returns the June 4 bar, because June 5's bar isn't known until 16:00. **The numbers below are made up.** Tiingo's terms don't allow sharing its data, so examples and test fixtures use synthetic prices.

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": null,
  "data": {
    "ticker": "AAPL",
    "cik": 320193,
    "session_date": "2020-06-04",
    "open": 100.0,
    "high": 101.5,
    "low": 99.25,
    "close": 101.0,
    "volume": 1000000,
    "available_at": "2020-06-04T16:00:00-04:00",
    "time_assumed": false,
    "source": "tiingo",
    "source_ref": "AAPL 2020-06-04"
  },
  "reason": null
}
```

`cik` is `null` for securities without one. On an early-close day, `available_at` is 13:00 ET.

**Display rights.** Until Tiingo display rights are settled (D2), a deployment can turn raw prices off with a backend setting. This endpoint then returns 403 `prices_restricted`, so the page should show the reason rather than an error.

### `GET /v1/filings/{ticker}/latest`

The latest filing of one form type that EDGAR had accepted by the knowledge time.

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |
| `form` | No | `10-K`, `10-Q`, or `8-K`. Default: `10-Q`. |
| `include_amendments` | No | `true` to also count amendments, such as 10-Q/A. Default: `false`. |

`GET /v1/filings/AAPL/latest?as_of=2020-06-05&form=10-Q`:

```json
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": null,
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
  "data_version": null,
  "data": null,
  "reason": "No 10-Q from Facebook Inc had been accepted by EDGAR by May 21, 2012, 9:30 AM ET."
}
```

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
  "data_version": null,
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
| 422 | `invalid_request` | A parameter is missing or invalid, including `as_of` (bad format, or a time that never happened or happened twice). `details` lists each field. |
| 403 | `prices_restricted` | Raw prices are turned off on this deployment (D2) |
| 500 | `internal_error` | A bug. The message is generic and never includes internals. |

`message` is a sentence the page can show as is. `details` is `[]` except for `invalid_request`.

## TypeScript types

Until S8.6 generates them from OpenAPI, the frontend can copy these:

```ts
export type V1Response<T> = {
  knowledge_time: string;
  data_version: string | null;
  data: T | null; // for lists, T is an array, and [] means nothing was known yet
  reason: string | null;
};

type Provenance = {
  available_at: string;
  time_assumed: boolean;
  source: "alfred" | "edgar" | "tiingo";
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
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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
  document_url: string;
  index_url: string;
};

export type V1Error = {
  error: {
    code:
      | "invalid_request"
      | "unknown_ticker"
      | "unknown_series"
      | "prices_restricted"
      | "internal_error";
    message: string;
    details: { field: string; message: string }[];
  };
};
```

With `apiFetch` from `frontend/lib/api/client.ts`, a failed call throws `ApiError`, whose `body` is a `V1Error`.

## Browser access (CORS)

The backend allows requests from the local dev server (`http://localhost:3000`) and the Vercel deployments, configured by a backend setting (S8.1). Until that ships, call the API from the server, as `getApiHealth` does.

## Coming after M2

| Endpoint | Story | Sprint |
| --- | --- | --- |
| `GET /v1/macro/{series_id}/revisions` | S4.5 | 3 |
| `GET /v1/fundamentals/{ticker}` | S5.7, S8.2 | 3 |
| `GET /v1/snapshot` | S8.3 | 3 |
| `GET /v1/catalog/series`, `/companies`, `/signals` | S8.5 | 3 |
| `POST /v1/backtests`, `GET /v1/backtests/{id}`, `GET /v1/backtests/{id}/audit` | S8.4 | 4 |

A price history and a whole macro series as known at a time (`get_price_history_as_of` and `get_macro_series_as_of`) will get endpoints when a page needs them, using the same envelope.
