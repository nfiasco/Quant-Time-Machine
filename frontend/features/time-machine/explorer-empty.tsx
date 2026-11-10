import Link from "next/link";
import { CalendarClockIcon, ListPlusIcon, TriangleAlertIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { demoQuery, explorerHref, suggestedQuery } from "@/features/time-machine/params";
import { formatEtDateTime, type EtDateTime } from "@/lib/time";

type ExplorerEmptyProps =
  | { kind: "blank" }
  | { kind: "moment-only"; moment: EtDateTime }
  | { kind: "invalid" };

// Solid, not dashed: in this app a dashed border means "not yet known".
const EMPTY_CLASS = "border border-solid bg-card";

/** What the results area shows before there's a snapshot to show, with a next step. */
export function ExplorerEmpty(props: ExplorerEmptyProps) {
  if (props.kind === "moment-only") {
    const suggestion = suggestedQuery(props.moment);
    return (
      <Empty className={EMPTY_CLASS}>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ListPlusIcon />
          </EmptyMedia>
          <EmptyTitle>Add a company or a series</EmptyTitle>
          <EmptyDescription>
            Choose what to look at on {formatEtDateTime(props.moment)}, then show what was
            known.
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button asChild>
            <Link href={explorerHref(suggestion)} scroll={false}>
              Show {joinWords([...suggestion.tickers, ...suggestion.series])}
            </Link>
          </Button>
        </EmptyContent>
      </Empty>
    );
  }

  if (props.kind === "invalid") {
    return (
      <Empty className={EMPTY_CLASS}>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <TriangleAlertIcon />
          </EmptyMedia>
          <EmptyTitle>This link has a problem</EmptyTitle>
          <EmptyDescription>
            Fix the highlighted fields above and show what was known, or start over with
            the example.
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button asChild variant="outline">
            <Link href={explorerHref(demoQuery)} scroll={false}>
              Start over with the example
            </Link>
          </Button>
        </EmptyContent>
      </Empty>
    );
  }

  return (
    <Empty className={EMPTY_CLASS}>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <CalendarClockIcon />
        </EmptyMedia>
        <EmptyTitle>Pick a moment to look back from</EmptyTitle>
        <EmptyDescription>
          Choose a date and time, then companies or economic series, to see what was public
          then and what wasn&apos;t yet.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button asChild>
          <Link href={explorerHref(demoQuery)} scroll={false}>
            Try {formatEtDateTime(demoQuery.moment)}
          </Link>
        </Button>
      </EmptyContent>
    </Empty>
  );
}

/** "AAPL, UNRATE, and FEDFUNDS". */
function joinWords(words: string[]): string {
  if (words.length <= 2) return words.join(" and ");
  return `${words.slice(0, -1).join(", ")}, and ${words.at(-1)}`;
}
