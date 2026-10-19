import { HistoryIcon } from "lucide-react";

import { siteConfig } from "@/config/site";
import { cn } from "@/lib/utils";

/** Logo mark plus wordmark. Pass `markOnly` where space is tight. */
export function Brand({
  markOnly = false,
  className,
}: {
  markOnly?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("flex min-w-0 items-center gap-2", className)}>
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <HistoryIcon className="size-4" aria-hidden />
      </span>
      {markOnly ? (
        <span className="sr-only">{siteConfig.name}</span>
      ) : (
        <span className="grid min-w-0 leading-tight">
          <span className="truncate text-sm font-semibold">{siteConfig.name}</span>
          <span className="truncate text-xs text-muted-foreground">
            Point-in-time research
          </span>
        </span>
      )}
    </span>
  );
}
