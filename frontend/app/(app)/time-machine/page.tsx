import { CalendarClockIcon, TriangleAlertIcon } from "lucide-react";

import { PlannedPage } from "@/components/feedback/planned-page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { routeMetadata, routes } from "@/config/navigation";
import { formatEtDateTime, parseAsOf, toAsOfParam } from "@/lib/time";

export const metadata = routeMetadata(routes.timeMachine);

export default async function TimeMachinePage(props: PageProps<"/time-machine">) {
  const { as_of: asOf } = await props.searchParams;
  const moment = parseAsOf(asOf);

  return (
    <PlannedPage route={routes.timeMachine}>
      {moment ? (
        <Alert variant="info">
          <CalendarClockIcon />
          <AlertTitle>Knowledge time: {formatEtDateTime(moment)}</AlertTitle>
          <AlertDescription>
            <p>
              The explorer will list everything that was public at this moment, and what
              wasn&apos;t yet. This link already carries the moment as{" "}
              <code className="font-mono text-xs whitespace-nowrap">
                as_of={toAsOfParam(moment)}
              </code>
              .
            </p>
          </AlertDescription>
        </Alert>
      ) : asOf ? (
        <Alert variant="warning">
          <TriangleAlertIcon />
          <AlertTitle>That knowledge time isn&apos;t valid</AlertTitle>
          <AlertDescription>
            <p>
              Use a date like <code className="font-mono text-xs">2020-06-05</code> (which
              means 09:30 ET) or a date and time like{" "}
              <code className="font-mono text-xs">2020-06-05T09:30</code>.
            </p>
          </AlertDescription>
        </Alert>
      ) : null}
    </PlannedPage>
  );
}
