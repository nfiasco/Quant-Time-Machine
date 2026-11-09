import type { MomentEvent } from "@/features/time-machine/moment-event";
import type { EtDateTime } from "@/lib/time";

/** The demo moment: June 5, 2020, at 09:30 ET (doc/roadmap.md §2.3). */
export const demoMoment: EtDateTime = {
  year: 2020,
  month: 6,
  day: 5,
  hour: 9,
  minute: 30,
};

/**
 * What was and wasn't public at the demo moment, in time order. Every time matches the
 * snapshot API's golden test (backend/tests/test_api_snapshot.py and doc/api-v1.md).
 * A static illustration for the dashboard; the Time Machine page (S9.2) shows the live
 * snapshot for any moment.
 */
export const demoMomentEvents: readonly MomentEvent[] = [
  {
    id: "aapl-q2-period-end",
    at: { year: 2020, month: 3, day: 28, hour: 9, minute: 30 },
    timeNote: "period end",
    label: "Apple's fiscal Q2 ends",
    detail: "A period end. The quarter's numbers aren't public until the 10-Q is accepted.",
    known: true,
  },
  {
    id: "aapl-q2-10q",
    at: { year: 2020, month: 4, day: 30, hour: 18, minute: 3 },
    label: "Apple's Q2 10-Q accepted by EDGAR",
    detail:
      "Usable from its acceptance time, not from the period end or the May 1 filing date.",
    known: true,
  },
  {
    id: "aapl-close-jun-4",
    at: { year: 2020, month: 6, day: 4, hour: 16, minute: 0 },
    label: "AAPL closes on June 4",
    detail: "A daily bar is known once its session closes.",
    known: true,
  },
  {
    id: "may-jobs-report",
    at: { year: 2020, month: 6, day: 5, hour: 8, minute: 30 },
    label: "May jobs report: unemployment 13.3%",
    detail: "The first print, released an hour before the decision.",
    known: true,
  },
  {
    id: "aapl-close-jun-5",
    at: { year: 2020, month: 6, day: 5, hour: 16, minute: 0 },
    label: "AAPL closes on June 5",
    detail: "Not known until 4:00 PM, after the 09:30 decision.",
    known: false,
  },
  {
    id: "aapl-q3-10q",
    at: { year: 2020, month: 7, day: 30, hour: 19, minute: 29 },
    label: "Apple's 10-Q for the quarter ended June 27",
    detail: "Accepted by EDGAR almost two months after the decision.",
    known: false,
  },
  {
    id: "may-unemployment-revised",
    at: { year: 2022, month: 1, day: 7, hour: 8, minute: 30 },
    label: "May 2020 unemployment revised to 13.2%",
    detail: "A later vintage. At the knowledge time, the number was 13.3%.",
    known: false,
  },
];
