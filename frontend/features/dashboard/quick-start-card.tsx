import Form from "next/form";
import Link from "next/link";
import { ArrowRightIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { routes } from "@/config/navigation";
import { demoMoment, demoMomentEvents } from "@/features/time-machine/example-moment";
import { KnowledgeHorizon } from "@/features/time-machine/knowledge-horizon";
import { formatEtDate, toAsOfParam } from "@/lib/time";

/** Dashboard hero: pick a knowledge time, with the demo moment explained below. */
export function QuickStartCard() {
  const demoAsOf = toAsOfParam(demoMoment);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Open the time machine</CardTitle>
        <CardDescription className="text-pretty">
          Pick a knowledge time. Everything you look at or test from there uses only
          what was public by then.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {/* A GET form: submitting navigates to /time-machine?as_of=…, so the moment lives in the URL. */}
        <Form
          action={routes.timeMachine.href}
          className="flex flex-col gap-3 sm:flex-row sm:items-start"
        >
          <Field className="sm:max-w-xs">
            <FieldLabel htmlFor="quick-start-as-of">Knowledge time (ET)</FieldLabel>
            <Input
              id="quick-start-as-of"
              name="as_of"
              type="datetime-local"
              defaultValue={demoAsOf}
              required
              className="font-mono tabular-nums"
            />
            <FieldDescription className="text-xs">
              New York time. A date alone means 09:30 ET.
            </FieldDescription>
          </Field>
          <Button type="submit" className="sm:mt-6">
            Open
            <ArrowRightIcon data-icon="inline-end" />
          </Button>
        </Form>

        <div className="flex flex-col gap-3">
          <h3 className="text-sm font-medium text-pretty">
            Example: what a researcher could see on {formatEtDate(demoMoment)}, at the
            market open
          </h3>
          <KnowledgeHorizon moment={demoMoment} events={demoMomentEvents} />
        </div>
      </CardContent>
      <CardFooter className="flex-col items-start gap-2 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <span>
          From the project&apos;s time model. Live answers arrive with the snapshot API.
        </span>
        <Link
          href={`/time-machine?as_of=${demoAsOf}`}
          className="flex items-center gap-1 rounded-sm font-medium text-foreground underline-offset-4 hover:underline"
        >
          Try this moment
          <ArrowRightIcon className="size-3.5" aria-hidden />
        </Link>
      </CardFooter>
    </Card>
  );
}
