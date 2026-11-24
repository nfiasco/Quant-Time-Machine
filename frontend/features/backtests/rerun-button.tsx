"use client";

import { useState, useTransition } from "react";
import { RotateCwIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { startBacktest } from "@/features/backtests/actions";
import { describeFailure } from "@/features/backtests/api-failure";
import type { ExperimentSpec } from "@/features/backtests/types";

/**
 * Submits a failed run's spec again (api-v1.md: a failed run runs again), as after a
 * restart stopped it. The same spec on the same data is the same run, so this page shows
 * it queued again.
 */
export function RerunButton({ spec }: { spec: ExperimentSpec }) {
  const [isPending, startTransition] = useTransition();
  const [problem, setProblem] = useState<string | null>(null);

  function rerun() {
    setProblem(null);
    startTransition(async () => {
      try {
        const failure = await startBacktest(spec);
        if (failure) {
          const { title, description } = describeFailure(failure);
          setProblem(`${title}. ${description}`);
        }
      } catch {
        setProblem("Couldn't submit the run. Try again.");
      }
    });
  }

  return (
    <div className="flex flex-col gap-2">
      {/* aria-disabled rather than disabled, so focus stays on it while the run is sent. */}
      <Button
        type="button"
        size="sm"
        aria-disabled={isPending || undefined}
        onClick={isPending ? undefined : rerun}
        className="self-start aria-disabled:opacity-50"
      >
        {isPending ? (
          <Spinner aria-hidden data-icon="inline-start" />
        ) : (
          <RotateCwIcon data-icon="inline-start" />
        )}
        Run it again
      </Button>
      {problem ? (
        <p role="alert" className="text-sm text-pretty text-destructive">
          {problem}
        </p>
      ) : null}
    </div>
  );
}
