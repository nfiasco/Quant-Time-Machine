import { chooseDecision, decisionDays, type DecisionChoice } from "@/features/backtests/decisions";
import {
  getBacktestAudit,
  getBacktestCoverage,
  getBacktestHoldings,
  getBacktestMembers,
  getBacktestTrades,
} from "@/lib/api/backtests";
import { settle, type Settled } from "@/lib/api/errors";
import type { BacktestResult, GetResponse } from "@/lib/api/types";

/** What a succeeded run's results page reads beyond the run itself (S9.6). */
export type RunResultsData = {
  /** The run's decision days, in order, for the picker. */
  days: string[];
  /** The decision the page drills into; null for a run without decisions. */
  choice: DecisionChoice | null;
  coverage: Settled<GetResponse<"/v1/backtests/{run_id}/coverage">>;
  /** The chosen decision's parts; null without a decision. */
  members: Settled<GetResponse<"/v1/backtests/{run_id}/members">> | null;
  holdings: Settled<GetResponse<"/v1/backtests/{run_id}/holdings">> | null;
  trades: Settled<GetResponse<"/v1/backtests/{run_id}/trades">> | null;
  audit: Settled<GetResponse<"/v1/backtests/{run_id}/audit">> | null;
};

/**
 * Reads a succeeded run's coverage and its chosen decision's members, holdings, trades,
 * and audit, all at once, each settled so its failure shows in its own place. Call it
 * from a Server Component, and only for a run that has succeeded: until then each part is
 * null, and the page refreshes every couple of seconds.
 */
export async function loadRunResults(
  runId: string,
  result: BacktestResult,
  decision: string | string[] | undefined,
): Promise<RunResultsData> {
  const days = decisionDays(result);
  const choice = chooseDecision(days, decision);
  const day = choice?.day;
  const [coverage, members, holdings, trades, audit] = await Promise.all([
    settle(getBacktestCoverage(runId)),
    day ? settle(getBacktestMembers(runId, day)) : null,
    day ? settle(getBacktestHoldings(runId, day)) : null,
    day ? settle(getBacktestTrades(runId, day)) : null,
    day ? settle(getBacktestAudit(runId, day)) : null,
  ]);
  return { days, choice, coverage, members, holdings, trades, audit };
}
