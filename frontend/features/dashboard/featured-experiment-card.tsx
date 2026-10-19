import Link from "next/link";
import { ArrowRightIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { canonicalPreset } from "@/features/backtests/presets";
import { SpecSummary } from "@/features/backtests/spec-summary";

/** The canonical experiment, ready to open in the builder. */
export function FeaturedExperimentCard({ className }: { className?: string }) {
  const { question, spec } = canonicalPreset;

  return (
    <Card className={className}>
      <CardHeader>
        <CardDescription>Featured experiment</CardDescription>
        <CardTitle>{spec.name}</CardTitle>
        <CardAction>
          <Badge variant="outline">Demo</Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <blockquote className="border-l-2 border-primary/40 pl-3 text-pretty text-muted-foreground italic">
          {question}
        </blockquote>
        <SpecSummary spec={spec} />
      </CardContent>
      <CardFooter className="flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-xs text-muted-foreground">
          The CISC 498 demo runs this backtest from the browser.
        </span>
        <Button asChild size="sm">
          <Link href={`/backtests/new?preset=${canonicalPreset.id}`}>
            Open in builder
            <ArrowRightIcon data-icon="inline-end" />
          </Link>
        </Button>
      </CardFooter>
    </Card>
  );
}
