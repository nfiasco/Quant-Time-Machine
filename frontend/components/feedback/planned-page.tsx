import Link from "next/link";
import {
  ArrowLeftIcon,
  ArrowUpRightIcon,
  CircleDashedIcon,
  LockIcon,
  MilestoneIcon,
} from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { milestones, routes, storyUrl, type AppRoute } from "@/config/navigation";

type PlannedPageProps = {
  route: AppRoute;
  /** Header buttons, for example a link to a related page that already works. */
  actions?: React.ReactNode;
  /** Optional preview shown above the plan, for example state read from the URL. */
  children?: React.ReactNode;
};

/**
 * Placeholder for a page that isn't built yet: what it will do, and which roadmap
 * story and milestone deliver it. Everything comes from config/navigation.ts.
 */
export function PlannedPage({ route, actions, children }: PlannedPageProps) {
  const { story, highlights = [] } = route;
  const milestone = story ? milestones[story.milestone] : undefined;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={route.title}
        description={route.description}
        actions={actions}
        badge={
          <>
            {story ? (
              <Badge variant="future">
                <CircleDashedIcon data-icon="inline-start" />
                Planned · {story.milestone}
              </Badge>
            ) : null}
            {route.requiresAccount ? (
              <Badge variant="outline">
                <LockIcon data-icon="inline-start" />
                Needs an account
              </Badge>
            ) : null}
          </>
        }
      />

      {children}

      <Card>
        <CardHeader>
          <CardTitle>What this page will do</CardTitle>
          <CardDescription>
            This page isn&apos;t built yet. Here&apos;s what the finished version is
            planned to include.
          </CardDescription>
        </CardHeader>
        {highlights.length > 0 ? (
          <CardContent>
            <ul className="flex flex-col gap-2.5">
              {highlights.map((highlight) => (
                <li key={highlight} className="flex gap-2.5 text-pretty">
                  <span
                    aria-hidden
                    className="mt-1.5 size-2 shrink-0 rounded-full border border-dashed border-future"
                  />
                  {highlight}
                </li>
              ))}
            </ul>
          </CardContent>
        ) : null}
        {story && milestone ? (
          <CardFooter className="flex-col items-start gap-1.5 text-muted-foreground sm:flex-row sm:items-center sm:gap-4">
            <span className="flex items-center gap-1.5">
              <MilestoneIcon className="size-4" aria-hidden />
              {story.milestone}: {milestone.name}, target {milestone.target}
            </span>
            <a
              href={storyUrl(story)}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 rounded-sm text-foreground underline-offset-4 hover:underline"
            >
              Story {story.id}: {story.title}
              <ArrowUpRightIcon className="size-3.5" aria-hidden />
              <span className="sr-only">(opens on GitHub)</span>
            </a>
          </CardFooter>
        ) : null}
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline">
          <Link href={routes.dashboard.href}>
            <ArrowLeftIcon data-icon="inline-start" />
            Back to dashboard
          </Link>
        </Button>
        {route.href !== routes.methodology.href ? (
          <Button asChild variant="ghost">
            <Link href={routes.methodology.href}>How point-in-time works</Link>
          </Button>
        ) : null}
      </div>
    </div>
  );
}
