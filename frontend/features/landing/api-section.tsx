import { siteConfig } from "@/config/site";

import {
  API_EXAMPLE_REQUEST,
  API_EXAMPLE_RESPONSE,
  tokenizeJsonc,
  type CodeToken,
} from "./api-example";

const TOKEN_CLASS: Record<CodeToken["kind"], string> = {
  key: "text-foreground",
  string: "text-muted-foreground",
  time: "text-brand-ink",
  literal: "text-foreground",
  comment: "text-muted-foreground italic",
  plain: "text-muted-foreground",
};

const tokens = tokenizeJsonc(API_EXAMPLE_RESPONSE);

const POINTS = [
  {
    title: "Every request names its moment.",
    body: "as_of is required, with no default: a default of “now” is exactly the trap.",
  },
  {
    title: "Every record shows its evidence.",
    body: "available_at says when it became public, and source says where it came from.",
  },
  {
    title: "The future is for teaching only.",
    body: "not_yet_known shows what a backtest must not see, and a test keeps the backtest engine from importing it.",
  },
];

export function ApiSection() {
  return (
    <section
      id="api"
      tabIndex={-1}
      aria-labelledby="api-title"
      className="border-t outline-none"
    >
      <div className="mx-auto grid w-full max-w-6xl gap-12 px-4 py-24 sm:px-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:px-8">
        <div>
          <h2
            id="api-title"
            className="text-3xl font-semibold tracking-tight sm:text-4xl"
          >
            The same answer, as data
          </h2>
          <p className="mt-3 text-base text-pretty text-muted-foreground sm:text-lg">
            The story above is one API call. Every endpoint takes a knowledge time
            and returns only what was public by then.
          </p>
          <ul className="mt-8 space-y-5">
            {POINTS.map((point) => (
              <li key={point.title} className="border-l-2 border-border pl-4">
                <p className="text-sm font-medium">{point.title}</p>
                <p className="mt-1 text-sm text-pretty text-muted-foreground">
                  {point.body}
                </p>
              </li>
            ))}
          </ul>
          <a
            href={siteConfig.apiDocUrl}
            target="_blank"
            rel="noreferrer"
            className="mt-8 inline-flex rounded-sm text-sm font-medium text-brand-ink underline-offset-4 hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            Read the API reference
          </a>
        </div>
        <figure className="min-w-0 overflow-hidden rounded-2xl border bg-card text-card-foreground shadow-xs">
          <div className="flex items-start gap-2 border-b px-4 py-3 font-mono text-xs">
            <span className="shrink-0 rounded-md bg-primary px-1.5 py-0.5 font-medium text-primary-foreground">
              GET
            </span>
            <span className="min-w-0 pt-0.5 break-all text-muted-foreground">
              {API_EXAMPLE_REQUEST}
            </span>
          </div>
          <pre className="max-h-[32rem] overflow-auto p-4 font-mono text-xs leading-relaxed">
            <code>
              {tokens.map((token, index) => (
                <span key={index} className={TOKEN_CLASS[token.kind]}>
                  {token.text}
                </span>
              ))}
            </code>
          </pre>
          <figcaption className="border-t px-4 py-3 text-xs text-pretty text-muted-foreground">
            The response on the test data, shortened. The API isn&apos;t publicly
            hosted yet.
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
