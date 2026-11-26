import { formatEtDate, formatEtTime, type EtDateTime } from "@/lib/time";
import { cn } from "@/lib/utils";

/**
 * The knowledge time T as a label: "T" in the brand ink over its date and its time in ET,
 * boxed in the amber that marks T everywhere (GUIDELINES.md §2). The Time Machine's
 * knowledge horizon sets it on its line, and a backtest's audit beside each view.
 */
export function KnowledgeTimeLabel({
  moment,
  className,
}: {
  moment: EtDateTime;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "flex flex-col items-center rounded-lg border border-primary/50 bg-background px-3 py-1.5 text-center shadow-xs",
        className,
      )}
    >
      <span className="font-mono text-sm font-semibold text-brand-ink">
        T<span className="sr-only">, the knowledge time:</span>
      </span>
      <span className="text-xs whitespace-nowrap text-muted-foreground">
        {formatEtDate(moment)}
      </span>
      <span className="font-mono text-xs whitespace-nowrap tabular-nums">
        {formatEtTime(moment)}
      </span>
    </p>
  );
}
