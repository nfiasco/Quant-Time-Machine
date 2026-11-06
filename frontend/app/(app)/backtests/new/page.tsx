
import { CircleDashedIcon } from "lucide-react";

import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { routeMetadata, routes } from "@/config/navigation";
import { BacktestBuilder } from "@/features/backtests/backtest-builder";
import { findPreset } from "@/features/backtests/presets";

export const metadata = routeMetadata(routes.backtestBuilder);

export default async function NewBacktestPage(
  props: PageProps<"/backtests/new">
) {
  const { preset: presetId } = await props.searchParams;
  const preset = findPreset(presetId);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={routes.backtestBuilder.title}
        description={routes.backtestBuilder.description}
        badge={
          <Badge variant="future">
            <CircleDashedIcon data-icon="inline-start" />
            In progress · M5
          </Badge>
        }
      />

      {preset ? (
        <blockquote className="border-l-2 border-primary/40 pl-3 text-sm text-pretty text-muted-foreground italic">
          {preset.question}
        </blockquote>
      ) : null}

      <BacktestBuilder
        key={preset?.id ?? "default"}
        initialSpec={preset?.spec}
      />
    </div>
  );
}
