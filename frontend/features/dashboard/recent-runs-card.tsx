import Link from "next/link";
import { ChartLineIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { routes } from "@/config/navigation";
import { canonicalPreset } from "@/features/backtests/presets";

/**
 * Recent runs. Always empty until runs can be saved (S16.5); then list the signed-in
 * user's latest runs here and keep this empty state for new accounts.
 */
export function RecentRunsCard({ className }: { className?: string }) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Recent runs</CardTitle>
        <CardDescription>Your latest backtests, newest first.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1">
        <Empty className="border border-dashed">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ChartLineIcon />
            </EmptyMedia>
            <EmptyTitle>No runs yet</EmptyTitle>
            <EmptyDescription>
              Runs you start from the builder will show up here. Once accounts launch,
              sign in to keep them between visits.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <div className="flex flex-wrap justify-center gap-2">
              <Button asChild size="sm">
                <Link href={`/backtests/new?preset=${canonicalPreset.id}`}>
                  Start from the example
                </Link>
              </Button>
              <Button asChild size="sm" variant="outline">
                <Link href={routes.signIn.href}>Sign in</Link>
              </Button>
            </div>
          </EmptyContent>
        </Empty>
      </CardContent>
    </Card>
  );
}
