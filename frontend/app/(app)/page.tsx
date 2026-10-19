import Link from "next/link";
import { Suspense } from "react";
import { CalendarClockIcon, PlusIcon } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { Button } from "@/components/ui/button";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";
import {
  ApiOfflineHint,
  ApiStatus,
  ApiStatusPending,
} from "@/features/dashboard/api-status";
import { FeaturedExperimentCard } from "@/features/dashboard/featured-experiment-card";
import { HowItWorks } from "@/features/dashboard/how-it-works";
import { QuickStartCard } from "@/features/dashboard/quick-start-card";
import { RecentRunsCard } from "@/features/dashboard/recent-runs-card";

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <PageHeader
          title="Dashboard"
          description={siteConfig.tagline}
          badge={
            <Suspense fallback={<ApiStatusPending />}>
              <ApiStatus />
            </Suspense>
          }
          actions={
            <>
              <Button asChild variant="outline">
                <Link href={routes.backtestBuilder.href}>
                  <PlusIcon data-icon="inline-start" />
                  New backtest
                </Link>
              </Button>
              <Button asChild>
                <Link href={routes.timeMachine.href}>
                  <CalendarClockIcon data-icon="inline-start" />
                  Open time machine
                </Link>
              </Button>
            </>
          }
        />
        <Suspense fallback={null}>
          <ApiOfflineHint />
        </Suspense>
      </div>

      <QuickStartCard />

      <div className="grid gap-6 lg:grid-cols-5">
        <FeaturedExperimentCard className="lg:col-span-3" />
        <RecentRunsCard className="lg:col-span-2" />
      </div>

      <HowItWorks />
    </div>
  );
}
