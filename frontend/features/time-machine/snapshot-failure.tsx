import { CircleAlertIcon } from "lucide-react";

import { ErrorState } from "@/components/feedback/error-state";
import { RetryButton } from "@/components/feedback/retry-button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { API_URL } from "@/lib/api/client";
import type { ApiFailure } from "@/lib/api/errors";

type SnapshotFailureProps = {
  failure: ApiFailure;
  /** The form already shows the message next to the field to change. */
  onField: boolean;
};

/** Why there's no snapshot, and what to do about it. */
export function SnapshotFailure({ failure, onField }: SnapshotFailureProps) {
  // The API rejected the request (a 4xx): retrying won't help, changing it will.
  if (failure.kind === "response" && failure.status < 500) {
    return (
      <Alert variant="destructive">
        <CircleAlertIcon />
        <AlertTitle>No snapshot for this request</AlertTitle>
        <AlertDescription>
          <p>{failure.message}</p>
          {onField ? <p>Change the highlighted field above and try again.</p> : null}
        </AlertDescription>
      </Alert>
    );
  }

  const { title, description } =
    failure.kind === "timeout"
      ? {
          title: "The research API took too long",
          description: "It didn't answer within 10 seconds. Try again in a moment.",
        }
      : failure.kind === "unreachable"
        ? {
            title: "Couldn't reach the research API",
            description:
              process.env.NODE_ENV === "development"
                ? `Nothing answered at ${API_URL}. Start the backend with "cd backend && uv run fastapi dev", then try again.`
                : `Nothing answered at ${API_URL}. Try again in a moment.`,
          }
        : { title: "The research API had a problem", description: failure.message };

  return <ErrorState title={title} description={description} actions={<RetryButton />} />;
}
