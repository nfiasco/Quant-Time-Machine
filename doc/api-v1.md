# Research API v1: response contract

> **Stories S8.1 and S8.2.** Drafted 2026-10-19 as the contract for S9.1's M2 demo page, and implemented in Sprint 2. The API's own docs at `/docs` show the examples below, each labeled with the request that produces it. A test replays every one against the test fixtures, so they can't drift. S8.6 will generate TypeScript types from the OpenAPI schema. To change the contract, update this file and the backend in the same pull request, and tell the frontend. The [snapshot section](#draft-for-sprint-3-get-v1snapshot) is a draft for S8.3 (2026-10-29), ahead of its code.

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

`GET /v1/knowledge-time?as_of=…` is the one exception. It only resolves an `as_of` value, so it returns just the first two fields, with the data version the data endpoints read now:

```json
{ "knowledge_time": "2020-06-05T09:30:00-04:00", "data_version": "20261019T120000Z" }
```

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

## Draft for Sprint 3: `GET /v1/snapshot`

> **Story S8.3, drafted 2026-10-29 for S9.2's Time Machine explorer. Nothing serves it yet.** It follows the conventions above and S8.3's acceptance criteria. In the example, `…` stands for values that S8.3 fills in when it adds the real, tested example to `app/api/examples.py`. Raise changes before S8.3 is built.

What was known at a moment, and what wasn't yet, for chosen companies and series. It reproduces the June 5, 2020 table in [roadmap §2.3](roadmap.md#23-example-june-5-2020-at-930-am-et).

| Parameter | Required | Meaning |
| --- | --- | --- |
| `as_of` | Yes | Knowledge time |
| `tickers` | At least one of `tickers` and `series` | Comma-separated, such as `AAPL,MSFT`; up to 10. Each is resolved as of the knowledge time. |
| `series` | At least one of `tickers` and `series` | Comma-separated series IDs, such as `UNRATE,CPIAUCSL`; up to 10 |

- **Neither one given, or more than 10,** is a 422 `invalid_request` naming the parameter.
- **A repeated entry counts once,** and results keep the order given.
- **An unknown ticker or series** fails the whole request with 404 `unknown_ticker` or `unknown_series`, naming it, as the single-item endpoints do.

`data` always has two sections, so it's never `null`, and `reason` is always `null`:

| Section | Holds | Rule |
| --- | --- | --- |
| `known` | For each company: the latest daily bar, and the latest 10-K, 10-Q, and 8-K. For each series: the latest observation. | Every record's `available_at` is at or before `knowledge_time`. It's read through `PointInTimeView`, like every other endpoint. |
| `not_yet_known` | For each company: the next bar to close, the next 10-K, 10-Q, and 8-K, and later amendments to filings already accepted. For each series: the later versions of the observation in `known`. | Every record's `available_at` is after `knowledge_time`. It comes from a separate look-ahead function that exists only for teaching, and a test keeps the engine from importing it (S8.3). |

`not_yet_known` shows what a backtest must not see, so never feed it into anything else.

`GET /v1/snapshot?as_of=2020-06-05&tickers=AAPL&series=UNRATE`, on a deployment where raw prices are off:

```jsonc
{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data_version": "…",
  "data": {
    "known": {
      "companies": [
        {
          "ticker": "AAPL",
          "cik": 320193,
          "company_name": "Apple Inc.",
          "prices_withheld": true,
          // A PriceBar, as in GET /v1/prices/{ticker}. Its prices are null because
          // prices_withheld is true; its date and available_at still show.
          "latest_bar": {
            "ticker": "AAPL",
            "cik": 320193,
            "session_date": "2020-06-04",
            "open": null,
            "high": null,
            "low": null,
            "close": null,
            "volume": null,
            "available_at": "2020-06-04T16:00:00-04:00",
            "time_assumed": false,
            "source": "tiingo",
            "source_ref": "tiingo AAPL 2020-06-04"
          },
          // Each is a Filing, as in GET /v1/filings/{ticker}/latest, or null.
          "latest_filings": {
            "10-K": { "accession_number": "…", "available_at": "…" },
            "10-Q": {
              "accession_number": "0000320193-20-000052",
              "form": "10-Q",
              "period_of_report": "2020-03-28",
              "available_at": "2020-04-30T18:03:10-04:00"
            },
            "8-K": { "accession_number": "…", "available_at": "…" }
          }
        }
      ],
      "series": [
        {
          "series_id": "UNRATE",
          // A MacroObservation, as in GET /v1/macro/{series_id}, or null.
          "latest": {
            "series_id": "UNRATE",
            "period": "2020-05-01",
            "value": 13.3,
            "vintage_date": "2020-06-05",
            "available_at": "2020-06-05T08:30:00-04:00"
          }
        }
      ]
    },
    "not_yet_known": {
      "companies": [
        {
          "ticker": "AAPL",
          "next_bar": {
            "session_date": "2020-06-05",
            "available_at": "2020-06-05T16:00:00-04:00"
          },
          "next_filings": {
            "10-K": { "accession_number": "…", "available_at": "…" },
            "10-Q": {
              "accession_number": "0000320193-20-000062",
              "form": "10-Q",
              "period_of_report": "2020-06-27",
              "available_at": "2020-07-30T19:29:09-04:00"
            },
            "8-K": { "accession_number": "…", "available_at": "…" }
          },
          "later_amendments": []
        }
      ],
      "series": [
        {
          "series_id": "UNRATE",
          "period": "2020-05-01",
          // Every later version of May 2020, oldest first, each a MacroObservation.
          // The last is today's value, 13.2%.
          "revisions": [
            { "period": "2020-05-01", "value": 13.2, "vintage_date": "…", "available_at": "…" }
          ]
        }
      ]
    }
  },
  "reason": null
}
```

- **`prices_withheld`** is `true` when the backend's `SERVE_RAW_PRICES` setting is off, as on the deployment (D2). Then `latest_bar` keeps its `session_date` and `available_at`, so the page can still say June 4's close was known, but its prices and `volume` are `null`. Unlike `GET /v1/prices`, the snapshot never answers 403.
- **`latest_bar`** is `null` when no bar from a closed session is in our data. **`next_bar`** is the next session to close after the knowledge time, from the NYSE calendar. It's `null` when the security has no later bar in our data, for example after its last trading day. It never carries prices: those weren't known yet.
- **`latest_filings` and `next_filings`** always have the keys `10-K`, `10-Q`, and `8-K`, each a `Filing` or `null`. They count original filings only. `next_filings` holds the first of each form accepted after the knowledge time.
- **`later_amendments`** lists amendments, such as a 10-Q/A, that EDGAR accepted after the knowledge time for filings it had accepted by then. Oldest first, up to 10.
- **`series[].latest`** is `null` when nothing had been published yet. Its `not_yet_known` entry then has `period: null` and `revisions: []`.
- **`revisions`** is `[]` when the observation shown was never revised later.
- **"Not yet known" means not public at the knowledge time, but in our data now.** It's limited to the response's `data_version`.
- **Fundamentals and universe membership** are in the time model's version of the table but not in S8.3's acceptance criteria. Revenue as known then has its own endpoint, `GET /v1/fundamentals/{ticker}` (S5.7). Either section can be added to the snapshot later without breaking this shape.

TypeScript, using the types above:

```ts
type FilingsByForm = { "10-K": Filing | null; "10-Q": Filing | null; "8-K": Filing | null };

export type SnapshotCompanyKnown = {
  ticker: string;
  cik: number | null;
  company_name: string;
  prices_withheld: boolean;
  latest_bar: PriceBar | null;
  latest_filings: FilingsByForm;
};

export type SnapshotCompanyNotYetKnown = {
  ticker: string;
  next_bar: { session_date: string; available_at: string } | null;
  next_filings: FilingsByForm;
  later_amendments: Filing[];
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

// GET /v1/snapshot returns V1Response<Snapshot>.
```

## Coming after M2

| Endpoint | Story | Sprint |
| --- | --- | --- |
| `GET /v1/macro/{series_id}/revisions` | S4.5 | 3 |
| `GET /v1/fundamentals/{ticker}` | S5.7, S8.2 | 3 |
| `GET /v1/snapshot` | S8.3 ([draft above](#draft-for-sprint-3-get-v1snapshot)) | 3 |
| `GET /v1/catalog/series`, `/companies`, `/signals` | S8.5 | 3 |
| `POST /v1/backtests`, `GET /v1/backtests/{id}`, `GET /v1/backtests/{id}/audit` | S8.4 | 4 |

A price history and a whole macro series as known at a time (`get_price_history_as_of` and `get_macro_series_as_of`) will get endpoints when a page needs them, using the same envelope.
