import Link from "next/link";
import { RotateCcwIcon, TriangleAlertIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { routes } from "@/config/navigation";

type ErrorStateProps = {
  title?: string;
  description?: string;
  /** Shown so a server-side error can be matched to its log entry. */
  digest?: string;
  /** Renders a "Try again" button; pass `retry` from an error.tsx boundary. */
  onRetry?: () => void;
};

/** Something failed: say what happened and offer a way forward. */
export function ErrorState({
  title = "Something went wrong",
  description = "This part of the page couldn't load. Try again, or go back to the dashboard.",
  digest,
  onRetry,
}: ErrorStateProps) {
  return (
    <Empty className="border border-destructive/30 bg-destructive/5">
      <EmptyHeader>
        <EmptyMedia variant="icon" className="bg-destructive/10 text-destructive">
          <TriangleAlertIcon />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <div className="flex flex-wrap justify-center gap-2">
          {onRetry ? (
            <Button onClick={onRetry}>
              <RotateCcwIcon data-icon="inline-start" />
              Try again
            </Button>
          ) : null}
          <Button asChild variant="outline">
            <Link href={routes.dashboard.href}>Back to dashboard</Link>
          </Button>
        </div>
        {digest ? (
          <p className="font-mono text-xs text-muted-foreground">Error ID: {digest}</p>
        ) : null}
      </EmptyContent>
    </Empty>
  );
}
