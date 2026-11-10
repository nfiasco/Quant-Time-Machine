import type { Snapshot, V1Response } from "@/lib/api/types";

/**
 * GET /v1/snapshot?as_of=2020-06-05&tickers=AAPL,TSLA&series=UNRATE,FEDFUNDS, as the API
 * documents it: the "june_5_2020" example in its OpenAPI schema (backend/app/api/examples.py),
 * which the backend replays against its test fixtures. Test data, not production: the 10-K
 * is a 2001 10-K405 with an assumed time, the 10-Q/A is made up, and TSLA has no bars or
 * filings. `satisfies` makes `next build` fail if lib/api/types.ts drifts from the API.
 *
 * To refresh it, with the backend running:
 *   curl -s localhost:8000/openapi.json | jq '.paths["/v1/snapshot"].get.responses["200"].content["application/json"].examples.june_5_2020.value'
 */
export const june5Snapshot = {
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
            "source_ref": "made up: AAPL 2020-06-04"
          },
          "latest_filings": {
            "10-K": {
              "ticker": "AAPL",
              "cik": 320193,
              "company_name": "Apple Inc.",
              "form": "10-K405",
              "is_amendment": false,
              "amends": null,
              "time_assumed": true,
              "source": "edgar",
              "accession_number": "0000912057-01-544436",
              "period_of_report": "2001-09-29",
              "filing_date": "2001-12-21",
              "available_at": "2001-12-21T23:59:59.999999-05:00",
              "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000091205701544436/a2066171z10-k405.htm",
              "index_url": "https://www.sec.gov/Archives/edgar/data/320193/000091205701544436/0000912057-01-544436-index.htm",
              "source_ref": "0000912057-01-544436"
            },
            "10-Q": {
              "ticker": "AAPL",
              "cik": 320193,
              "company_name": "Apple Inc.",
              "form": "10-Q",
              "is_amendment": false,
              "amends": null,
              "time_assumed": false,
              "source": "edgar",
              "accession_number": "0000320193-20-000052",
              "period_of_report": "2020-03-28",
              "filing_date": "2020-05-01",
              "available_at": "2020-04-30T18:03:10-04:00",
              "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/a10-qq220203282020.htm",
              "index_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000052/0000320193-20-000052-index.htm",
              "source_ref": "0000320193-20-000052"
            },
            "8-K": {
              "ticker": "AAPL",
              "cik": 320193,
              "company_name": "Apple Inc.",
              "form": "8-K",
              "is_amendment": false,
              "amends": null,
              "time_assumed": false,
              "source": "edgar",
              "accession_number": "0000320193-20-000050",
              "period_of_report": "2020-04-30",
              "filing_date": "2020-04-30",
              "available_at": "2020-04-30T16:30:41-04:00",
              "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000050/a8-kq220203282020.htm",
              "index_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000050/0000320193-20-000050-index.htm",
              "source_ref": "0000320193-20-000050"
            }
          },
          "latest_revenue": {
            "ticker": "AAPL",
            "cik": 320193,
            "metric": "revenue",
            "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "unit": "USD",
            "time_assumed": false,
            "source": "edgar",
            "period_start": "2019-12-29",
            "period_end": "2020-03-28",
            "fiscal_year": 2020,
            "fiscal_period": "Q2",
            "value": 58313000000,
            "derived": false,
            "accession_numbers": [
              "0000320193-20-000052"
            ],
            "available_at": "2020-04-30T18:03:10-04:00",
            "source_ref": "0000320193-20-000052"
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
          "latest_filings": {
            "10-K": null,
            "10-Q": null,
            "8-K": null
          },
          "latest_revenue": null,
          "universes": []
        }
      ],
      "series": [
        {
          "series_id": "UNRATE",
          "latest": {
            "series_id": "UNRATE",
            "title": "Unemployment Rate",
            "units": "Percent",
            "frequency": "Monthly",
            "seasonal_adjustment": "Seasonally Adjusted",
            "release": "Employment Situation",
            "time_assumed": false,
            "source": "alfred",
            "period": "2020-05-01",
            "value": 13.3,
            "vintage_date": "2020-06-05",
            "available_at": "2020-06-05T08:30:00-04:00",
            "source_ref": "UNRATE vintage 2020-06-05"
          }
        },
        {
          "series_id": "FEDFUNDS",
          "latest": {
            "series_id": "FEDFUNDS",
            "title": "Federal Funds Effective Rate",
            "units": "Percent",
            "frequency": "Monthly",
            "seasonal_adjustment": "Not Seasonally Adjusted",
            "release": "H.15 Selected Interest Rates",
            "period": "2020-05-01",
            "value": 0.05,
            "vintage_date": "2020-06-01",
            "available_at": "2020-06-01T16:15:00-04:00",
            "time_assumed": false,
            "source": "alfred",
            "source_ref": "FEDFUNDS vintage 2020-06-01"
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
            "10-K": {
              "ticker": "AAPL",
              "cik": 320193,
              "company_name": "Apple Inc.",
              "form": "10-K",
              "is_amendment": false,
              "amends": null,
              "time_assumed": false,
              "source": "edgar",
              "accession_number": "0000320193-20-000096",
              "period_of_report": "2020-09-26",
              "filing_date": "2020-10-30",
              "available_at": "2020-10-29T18:06:25-04:00",
              "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000096/aapl-20200926.htm",
              "index_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000096/0000320193-20-000096-index.htm",
              "source_ref": "0000320193-20-000096"
            },
            "10-Q": {
              "ticker": "AAPL",
              "cik": 320193,
              "company_name": "Apple Inc.",
              "form": "10-Q",
              "is_amendment": false,
              "amends": null,
              "time_assumed": false,
              "source": "edgar",
              "accession_number": "0000320193-20-000062",
              "period_of_report": "2020-06-27",
              "filing_date": "2020-07-31",
              "available_at": "2020-07-30T19:29:09-04:00",
              "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000062/aapl-20200627.htm",
              "index_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320000062/0000320193-20-000062-index.htm",
              "source_ref": "0000320193-20-000062"
            },
            "8-K": null
          },
          "later_amendments": [
            {
              "ticker": "AAPL",
              "cik": 320193,
              "company_name": "Apple Inc.",
              "form": "10-Q/A",
              "is_amendment": true,
              "amends": "0000320193-20-000052",
              "time_assumed": false,
              "source": "edgar",
              "accession_number": "0000320193-20-900001",
              "period_of_report": "2020-03-28",
              "filing_date": "2020-06-10",
              "available_at": "2020-06-10T16:00:00-04:00",
              "document_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320900001/amendment.htm",
              "index_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019320900001/0000320193-20-900001-index.htm",
              "source_ref": "made up: an amendment for the amendment tests"
            }
          ],
          "later_revenue": [
            {
              "ticker": "AAPL",
              "cik": 320193,
              "metric": "revenue",
              "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
              "unit": "USD",
              "time_assumed": false,
              "source": "edgar",
              "period_start": "2019-12-29",
              "period_end": "2020-03-28",
              "fiscal_year": 2020,
              "fiscal_period": "Q2",
              "value": 58313000000,
              "derived": false,
              "accession_numbers": [
                "0000320193-20-000096"
              ],
              "available_at": "2020-10-29T18:06:25-04:00",
              "source_ref": "0000320193-20-000096"
            },
            {
              "ticker": "AAPL",
              "cik": 320193,
              "metric": "revenue",
              "concept": "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
              "unit": "USD",
              "time_assumed": false,
              "source": "edgar",
              "period_start": "2019-12-29",
              "period_end": "2020-03-28",
              "fiscal_year": 2020,
              "fiscal_period": "Q2",
              "value": 58313000000,
              "derived": false,
              "accession_numbers": [
                "0000320193-21-000056"
              ],
              "available_at": "2021-04-28T18:02:54-04:00",
              "source_ref": "0000320193-21-000056"
            }
          ],
          "universe_changes": []
        },
        {
          "ticker": "TSLA",
          "next_bar": null,
          "next_filings": {
            "10-K": null,
            "10-Q": null,
            "8-K": null
          },
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
        {
          "series_id": "UNRATE",
          "period": "2020-05-01",
          "revisions": [
            {
              "series_id": "UNRATE",
              "title": "Unemployment Rate",
              "units": "Percent",
              "frequency": "Monthly",
              "seasonal_adjustment": "Seasonally Adjusted",
              "release": "Employment Situation",
              "time_assumed": false,
              "source": "alfred",
              "period": "2020-05-01",
              "value": 13.2,
              "vintage_date": "2022-01-07",
              "available_at": "2022-01-07T08:30:00-05:00",
              "source_ref": "UNRATE vintage 2022-01-07"
            }
          ]
        },
        {
          "series_id": "FEDFUNDS",
          "period": "2020-05-01",
          "revisions": []
        }
      ]
    }
  },
  "reason": null
} satisfies V1Response<Snapshot>;
