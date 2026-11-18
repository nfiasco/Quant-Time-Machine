// Client-side checks for the backtest builder: the rules in
// backend/app/backtest/spec.py that the ExperimentSpec type can't express. The API
// stays the source of truth; these give instant feedback. Errors are keyed by the
// same dotted field paths as the API's 422 errors ("period.end", "costs.bps_per_trade"),
// so server errors can be shown in the same places later (S9.5).

import type { ExperimentSpec } from "@/features/backtests/types";

export type SpecErrors = Partial<Record<string, string>>;

const DECISION = /^first_trading_day ([01][0-9]|2[0-3]):([0-5][0-9]) America\/New_York$/;
const TICKER = /^[A-Z0-9][A-Z0-9.-]*$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

/** "first_trading_day 09:30 America/New_York" → "09:30", or undefined if malformed. */
export function decisionTime(decision: string): string | undefined {
  const match = DECISION.exec(decision);
  return match ? `${match[1]}:${match[2]}` : undefined;
}

/** "09:30" → "first_trading_day 09:30 America/New_York". */
export function decisionFromTime(time: string): string {
  return `first_trading_day ${time} America/New_York`;
}

/**
 * A spec's assumed delisting return as the builder's loss field shows it, in percent:
 * -0.3 → "30". The field asks for a loss so that a phone's number pad, which often has
 * no minus key, can enter it.
 */
export function delistingLoss(delisting: ExperimentSpec["delisting"]): string {
  const loss = -(delisting?.assumed_return ?? 0) * 100;
  // Rounding drops floating-point noise (-0.07 * 100 is 7.000000000000001), and
  // `|| 0` writes -0 as 0.
  return String(Number(loss.toPrecision(12)) || 0);
}

/** The loss field's text as a spec's delisting section: "30" → -0.3. A blank field is
 * NaN, so it shows an error instead of becoming 0. */
export function delistingFromLoss(text: string): NonNullable<ExperimentSpec["delisting"]> {
  const loss = text.trim() === "" ? Number.NaN : Number(text);
  return { assumed_return: -loss / 100 };
}

export function validateSpec(spec: ExperimentSpec): SpecErrors {
  const errors: SpecErrors = {};

  if (!spec.name.trim()) {
    errors.name = "Name can't be blank.";
  }

  if (!DATE.test(spec.period.start)) {
    errors["period.start"] = "Enter a start date.";
  }
  if (!DATE.test(spec.period.end)) {
    errors["period.end"] = "Enter an end date.";
  } else if (DATE.test(spec.period.start) && spec.period.end <= spec.period.start) {
    errors["period.end"] = "End date must be after the start date.";
  }

  const time = decisionTime(spec.schedule.decision);
  if (!time) {
    errors["schedule.decision"] = "Enter a decision time.";
  } else if (spec.schedule.fill === "same_day_close" && time >= "16:00") {
    errors["schedule.decision"] =
      "A same-day close fill needs a decision before the 16:00 ET close. Decide earlier, or fill at the next day's open.";
  }

  if (!TICKER.test(spec.benchmark)) {
    errors.benchmark = "Enter a ticker in capitals, such as SPY.";
  }

  const bps = spec.costs.bps_per_trade;
  if (!Number.isFinite(bps)) {
    errors["costs.bps_per_trade"] = "Enter a number of basis points.";
  } else if (bps < 0) {
    errors["costs.bps_per_trade"] = "Costs must be at least 0.";
  }

  const assumed = spec.delisting?.assumed_return ?? 0;
  if (!Number.isFinite(assumed)) {
    errors["delisting.assumed_return"] = "Enter a loss from 0 to 100%.";
  } else if (assumed < -1 || assumed > 0) {
    errors["delisting.assumed_return"] = "The loss must be from 0 to 100%.";
  }

  return errors;
}
