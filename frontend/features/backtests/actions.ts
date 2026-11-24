"use server";

import { redirect } from "next/navigation";

import type { ExperimentSpec } from "@/features/backtests/types";
import { isRunId, submitBacktest } from "@/lib/api/backtests";
import { settle, type ApiFailure } from "@/lib/api/errors";

/**
 * Submits a spec (S9.5) and opens its run's page: a saved run's at once, or one to watch
 * while the run goes. A Server Function is a public endpoint, so the spec is only passed on:
 * the API checks it, and a 422 comes back with each field's path for the form to place.
 * Any other failure comes back too, for the form to explain.
 */
export async function startBacktest(spec: ExperimentSpec): Promise<ApiFailure> {
  const submitted = await settle(submitBacktest(spec));
  if (!submitted.ok) return submitted.failure;
  const { run_id: runId } = submitted.value;
  if (!isRunId(runId)) throw new Error(`The API answered with a malformed run ID: ${runId}`);
  redirect(`/backtests/${runId}`);
}
