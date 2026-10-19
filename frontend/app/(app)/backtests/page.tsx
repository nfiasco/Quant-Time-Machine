import Link from "next/link";
import { PlusIcon } from "lucide-react";

import { PlannedPage } from "@/components/feedback/planned-page";
import { Button } from "@/components/ui/button";
import { routeMetadata, routes } from "@/config/navigation";

export const metadata = routeMetadata(routes.backtests);

export default function BacktestsPage() {
  return (
    <PlannedPage
      route={routes.backtests}
      actions={
        <Button asChild>
          <Link href={routes.backtestBuilder.href}>
            <PlusIcon data-icon="inline-start" />
            New backtest
          </Link>
        </Button>
      }
    />
  );
}
