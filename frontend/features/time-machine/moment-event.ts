import type { EtDateTime } from "@/lib/time";

/** One fact on the knowledge horizon: when it became public, and what it was. */
export type MomentEvent = {
  id: string;
  /** When it became public, New York time; for a period end, the day it describes. */
  at: EtDateTime;
  /** Shown instead of a time of day, for moments that don't have one. */
  timeNote?: string;
  label: string;
  /** One more line of context; may be empty. */
  detail: string;
  /** Public at or before the knowledge time. */
  known: boolean;
  /** Where to read the source, such as the filing on EDGAR. Only https links are shown. */
  link?: { href: string; label: string };
  /** A caveat about the record, such as a time assumed from a conservative default. */
  caveat?: string;
};
