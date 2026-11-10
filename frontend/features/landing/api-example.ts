// The landing page's API example: the scroll story's question as one request, and its
// response from the test data, shortened from doc/reference/api-v1.md ("GET /v1/snapshot").
// Prices stay null: the deployment withholds them (decision D2).

export const API_EXAMPLE_REQUEST =
  "/v1/snapshot?as_of=2020-06-05&tickers=AAPL,TSLA&series=UNRATE,FEDFUNDS";

export const API_EXAMPLE_RESPONSE = `{
  "knowledge_time": "2020-06-05T09:30:00-04:00",
  "data": {
    "known": {
      "companies": [
        {
          "ticker": "AAPL",
          "prices_withheld": true,
          "latest_bar": {
            "session_date": "2020-06-04",
            "close": null,
            "available_at": "2020-06-04T16:00:00-04:00"
          },
          "latest_revenue": {
            "period_end": "2020-03-28",
            "value": 58313000000.0,
            "available_at": "2020-04-30T18:03:10-04:00"
          }
          // …and the latest 10-K, 10-Q, and 8-K
        },
        { "ticker": "TSLA", "universes": [] }
      ],
      "series": [
        {
          "series_id": "UNRATE",
          "latest": {
            "value": 13.3,
            "available_at": "2020-06-05T08:30:00-04:00"
          }
        }
        // …and FEDFUNDS
      ]
    },
    "not_yet_known": {
      "companies": [
        {
          "ticker": "TSLA",
          "universe_changes": [
            { "change": "joins", "effective": "2020-12-21" }
          ]
        }
      ],
      "series": [
        {
          "series_id": "UNRATE",
          "revisions": [{ "value": 13.2, "vintage_date": "2022-01-07" }]
        }
      ]
    }
  }
}`;

export type CodeToken = {
  text: string;
  kind: "key" | "string" | "time" | "literal" | "comment" | "plain";
};

const TOKEN =
  /("(?:[^"\\]|\\.)*")(\s*:)?|(\/\/[^\n]*)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|\btrue\b|\bfalse\b|\bnull\b)/g;

/** Splits JSON with // comments into tokens to color. Timestamps get their own kind. */
export function tokenizeJsonc(source: string): CodeToken[] {
  const tokens: CodeToken[] = [];
  let index = 0;
  let key = "";
  for (const match of source.matchAll(TOKEN)) {
    const [whole, string, colon, comment, literal] = match;
    const start = match.index ?? 0;
    if (start > index) tokens.push({ text: source.slice(index, start), kind: "plain" });
    if (string && colon) {
      key = string;
      tokens.push({ text: string, kind: "key" }, { text: colon, kind: "plain" });
    } else if (string) {
      tokens.push({ text: string, kind: key === '"available_at"' ? "time" : "string" });
    } else if (comment) {
      tokens.push({ text: comment, kind: "comment" });
    } else {
      tokens.push({ text: literal, kind: "literal" });
    }
    index = start + whole.length;
  }
  if (index < source.length) tokens.push({ text: source.slice(index), kind: "plain" });
  return tokens;
}
