import type { EtDateTime } from "@/lib/time";

/** The demo moment: June 5, 2020, at 09:30 ET (doc/roadmap.md §2.3). */
export const demoMoment: EtDateTime = {
  year: 2020,
  month: 6,
  day: 5,
  hour: 9,
  minute: 30,
};

export type MomentEvent = {
  id: string;
  /** When it happened or became public, as the docs give it (some are approximate). */
  when: string;
  label: string;
  detail: string;
  /** Public at or before the knowledge time. */
  known: boolean;
};

/**
 * What was and wasn't public at the demo moment, in time order. Taken from the
 * acceptance-test table in doc/roadmap.md §2.3; an illustration until the snapshot
 * endpoint (S8.3) serves the real answer.
 */
export const demoMomentEvents: readonly MomentEvent[] = [
  {
    id: "aapl-q2-period-end",
    when: "Mar 28, 2020",
    label: "Apple's fiscal Q2 ends",
    detail: "A period end. The quarter's numbers aren't public until the 10-Q is accepted.",
    known: true,
  },
  {
    id: "aapl-q2-10q",
    when: "~May 1, 2020",
    label: "Apple's Q2 10-Q accepted by EDGAR",
    detail: "Usable from its acceptance time, not from the period end or the filing date.",
    known: true,
  },
  {
    id: "aapl-close-jun-4",
    when: "Jun 4, 4:00 PM ET",
    label: "AAPL closes on June 4",
    detail: "A daily bar is known once its session closes.",
    known: true,
  },
  {
    id: "may-jobs-report",
    when: "Jun 5, 8:30 AM ET",
    label: "May jobs report: unemployment 13.3%",
    detail: "The first print, released an hour before the decision.",
    known: true,
  },
  {
    id: "aapl-close-jun-5",
    when: "Jun 5, 4:00 PM ET",
    label: "AAPL closes on June 5",
    detail: "Not known until 4:00 PM, after the 09:30 decision.",
    known: false,
  },
  {
    id: "may-labor-revisions",
    when: "Later releases",
    label: "Revisions to May labor data",
    detail: "Published in later releases and annual revisions.",
    known: false,
  },
  {
    id: "aapl-q3-10q",
    when: "Late Jul 2020",
    label: "Apple's 10-Q for the quarter ended June 27",
    detail: "Not filed until late July.",
    known: false,
  },
];
