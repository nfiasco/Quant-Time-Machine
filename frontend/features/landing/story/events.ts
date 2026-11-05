// The scroll story's facts: what was known at June 5, 2020, 9:30 AM ET, and when each
// fact became public. Every value and timestamp comes from the snapshot golden test
// (backend/tests/test_api_snapshot.py), its fixtures (backend/tests/fixtures/), and
// doc/time-model.md. Change them only together with those.

import type { EtDateTime } from "@/lib/time";

/** The question's knowledge time T. */
export const KNOWLEDGE_TIME: EtDateTime = {
  year: 2020,
  month: 6,
  day: 5,
  hour: 9,
  minute: 30,
};

export const KNOWLEDGE_TIME_ISO = "2020-06-05T09:30:00-04:00";

/** The snapshot request the story answers, in the API's own parameters. */
export const STORY_QUERY = {
  question: "What was known on June 5, 2020, at 9:30 AM ET?",
  params: "as_of=2020-06-05T09:30 · tickers=AAPL,TSLA · series=UNRATE,FEDFUNDS",
} as const;

export type StoryEvent = {
  id: string;
  /**
   * `known`: public before T. `period`: a period end, which publishes nothing.
   * `later`: public only after T.
   */
  kind: "known" | "period" | "later";
  /** When it became public; for a period end, the day it describes. */
  at: EtDateTime;
  /** Shown instead of a time of day, for moments without one. */
  timeNote?: string;
  /** For <time dateTime>. */
  iso: string;
  title: string;
  value?: string;
  detail: string;
  /** What the stop shows about point-in-time data. */
  lesson: string;
};

/** The six stops before T, in order. */
export const STORY_STOPS: readonly StoryEvent[] = [
  {
    id: "apple-quarter-ends",
    kind: "period",
    at: { year: 2020, month: 3, day: 28, hour: 9, minute: 30 },
    timeNote: "Period end",
    iso: "2020-03-28",
    title: "Apple's fiscal second quarter ends",
    detail: "The quarter is over, but none of its numbers are public yet.",
    lesson: "Publication lag",
  },
  {
    id: "apple-10q",
    kind: "known",
    at: { year: 2020, month: 4, day: 30, hour: 18, minute: 3 },
    iso: "2020-04-30T18:03:10-04:00",
    title: "EDGAR accepts Apple's 10-Q",
    value: "$58,313M revenue",
    detail:
      "33 days after the quarter ended. It counts from its acceptance time, not the May 1 filing date: a 9:30 AM decision first sees it on May 1.",
    lesson: "Filings, as filed",
  },
  {
    id: "april-unemployment",
    kind: "known",
    at: { year: 2020, month: 5, day: 8, hour: 8, minute: 30 },
    iso: "2020-05-08T08:30:00-04:00",
    title: "April's unemployment rate",
    value: "14.7%",
    detail: "The first print, released with the jobs report at 8:30 AM.",
    lesson: "Economic data, by vintage",
  },
  {
    id: "may-fed-funds",
    kind: "known",
    at: { year: 2020, month: 6, day: 1, hour: 16, minute: 15 },
    iso: "2020-06-01T16:15:00-04:00",
    title: "May's fed funds rate",
    value: "0.05%",
    detail: "Published with the Federal Reserve's H.15 release at 4:15 PM.",
    lesson: "Release times",
  },
  {
    id: "aapl-june-4-close",
    kind: "known",
    at: { year: 2020, month: 6, day: 4, hour: 16, minute: 0 },
    iso: "2020-06-04T16:00:00-04:00",
    title: "AAPL's June 4 session closes",
    detail:
      "A day's prices are known at its close, not its open. (We don't show prices: our data license is for internal use.)",
    lesson: "Prices, at the close",
  },
  {
    id: "may-unemployment",
    kind: "known",
    at: { year: 2020, month: 6, day: 5, hour: 8, minute: 30 },
    iso: "2020-06-05T08:30:00-04:00",
    title: "May's unemployment rate",
    value: "13.3%",
    detail: "The first print. At 8:00 AM, you'd still have seen April's 14.7%.",
    lesson: "To the minute",
  },
];

/** Three facts that became public only after T. */
export const STORY_LATER: readonly StoryEvent[] = [
  {
    id: "aapl-june-5-close",
    kind: "later",
    at: { year: 2020, month: 6, day: 5, hour: 16, minute: 0 },
    iso: "2020-06-05T16:00:00-04:00",
    title: "AAPL's June 5 session closes",
    detail: "Six and a half hours after the knowledge time.",
    lesson: "The next bar",
  },
  {
    id: "tesla-joins",
    kind: "later",
    at: { year: 2020, month: 12, day: 21, hour: 9, minute: 30 },
    timeNote: "Before the open",
    iso: "2020-12-21",
    title: "Tesla joins the S&P 500",
    detail:
      "At the knowledge time it isn't in the universe, so a June 2020 decision can't include it.",
    lesson: "Universe, by effective date",
  },
  {
    id: "may-unemployment-revised",
    kind: "later",
    at: { year: 2022, month: 1, day: 7, hour: 8, minute: 30 },
    iso: "2022-01-07T08:30:00-05:00",
    title: "May 2020's unemployment rate is revised",
    value: "13.2%",
    detail: "The value you'd find today. On June 5, 2020, it was 13.3%.",
    lesson: "Revisions",
  },
];

export type SnapshotRow = {
  label: string;
  value: string;
  /** When it became public; omitted for facts about the moment itself. */
  at?: EtDateTime;
  note?: string;
};

/** The answer: the snapshot's `known` section, in words. */
export const SNAPSHOT_KNOWN: readonly SnapshotRow[] = [
  { label: "Unemployment rate, May", value: "13.3%", at: STORY_STOPS[5].at },
  { label: "Fed funds rate, May", value: "0.05%", at: STORY_STOPS[3].at },
  { label: "Apple revenue, fiscal Q2", value: "$58,313M", at: STORY_STOPS[1].at },
  { label: "AAPL, latest bar", value: "June 4 close", at: STORY_STOPS[4].at },
  { label: "TSLA", value: "Not in the universe", note: "As of the knowledge time" },
];
