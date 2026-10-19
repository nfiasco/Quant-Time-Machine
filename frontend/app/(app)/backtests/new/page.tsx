import { PlannedPage } from "@/components/feedback/planned-page";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { routeMetadata, routes } from "@/config/navigation";
import { findPreset } from "@/features/backtests/presets";
import { SpecSummary } from "@/features/backtests/spec-summary";

export const metadata = routeMetadata(routes.backtestBuilder);

export default async function NewBacktestPage(props: PageProps<"/backtests/new">) {
  const { preset: presetId } = await props.searchParams;
  const preset = findPreset(presetId);

  return (
    <PlannedPage route={routes.backtestBuilder}>
      {preset ? (
        <Card>
          <CardHeader>
            <CardDescription>Preset that will load into the builder</CardDescription>
            <CardTitle>{preset.spec.name}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <blockquote className="border-l-2 border-primary/40 pl-3 text-pretty text-muted-foreground italic">
              {preset.question}
            </blockquote>
            <SpecSummary spec={preset.spec} />
          </CardContent>
        </Card>
      ) : null}
    </PlannedPage>
  );
}
