"use client";

import { useOptimistic, useTransition } from "react";
import { useRouter } from "next/navigation";
import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  NativeSelect,
  NativeSelectOptGroup,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { decisionHref, formatDay } from "@/features/backtests/decisions";
import { formatEtShortDate, parseIsoDate } from "@/lib/time";

type RebalancePickerProps = {
  runId: string;
  /** The run's decision days, in order. */
  days: string[];
  /** The one the page shows. */
  selected: string;
};

/**
 * Picks the rebalance the results page drills into (S9.6). It puts the day in the address
 * as `?decision=`, the API's own name, so the view can be shared, and renders the page
 * again in a transition: the old rebalance stays, dimmed through `data-pending`, until the
 * new one is ready.
 */
export function RebalancePicker({ runId, days, selected }: RebalancePickerProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [shown, setShown] = useOptimistic(selected);
  const index = days.indexOf(shown);
  const previous = index > 0 ? days[index - 1] : null;
  const next = index >= 0 && index < days.length - 1 ? days[index + 1] : null;

  function go(day: string) {
    startTransition(() => {
      setShown(day);
      router.push(decisionHref(runId, day), { scroll: false });
    });
  }

  const years = new Map<string, string[]>();
  for (const day of days) {
    const year = day.slice(0, 4);
    years.set(year, [...(years.get(year) ?? []), day]);
  }

  return (
    <div data-pending={isPending ? "" : undefined} className="flex flex-col gap-1.5">
      <label htmlFor="rebalance-day" className="text-xs font-medium text-muted-foreground">
        Rebalance
      </label>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="icon"
          disabled={previous === null}
          onClick={() => previous && go(previous)}
          aria-label={
            previous ? `Previous rebalance, ${formatDay(previous)}` : "No earlier rebalance"
          }
        >
          <ChevronLeftIcon />
        </Button>
        <NativeSelect
          id="rebalance-day"
          value={shown}
          onChange={(event) => go(event.target.value)}
          className="w-44 font-mono tabular-nums"
        >
          {[...years].map(([year, inYear]) => (
            <NativeSelectOptGroup key={year} label={year}>
              {inYear.map((day) => (
                <NativeSelectOption key={day} value={day}>
                  {short(day)}
                </NativeSelectOption>
              ))}
            </NativeSelectOptGroup>
          ))}
        </NativeSelect>
        <Button
          type="button"
          variant="outline"
          size="icon"
          disabled={next === null}
          onClick={() => next && go(next)}
          aria-label={next ? `Next rebalance, ${formatDay(next)}` : "No later rebalance"}
        >
          <ChevronRightIcon />
        </Button>
      </div>
      <p role="status" className="text-xs text-muted-foreground">
        {isPending
          ? `Loading the rebalance of ${formatDay(shown)}…`
          : `${days.length} ${days.length === 1 ? "rebalance" : "rebalances"}; showing ${formatDay(selected)}.`}
      </p>
    </div>
  );
}

function short(day: string): string {
  const date = parseIsoDate(day);
  return date ? formatEtShortDate(date) : day;
}
