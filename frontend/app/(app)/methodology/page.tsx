import { BookOpenIcon } from "lucide-react";

import { PlannedPage } from "@/components/feedback/planned-page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { routeMetadata, routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";

export const metadata = routeMetadata(routes.methodology);

export default function MethodologyPage() {
  return (
    <PlannedPage route={routes.methodology}>
      <Alert variant="info">
        <BookOpenIcon />
        <AlertTitle>The rules are already written down</AlertTitle>
        <AlertDescription>
          <p>
            Until this page ships, the{" "}
            <a href={siteConfig.timeModelUrl} target="_blank" rel="noreferrer">
              time model
            </a>{" "}
            explains how &ldquo;known at time T&rdquo; works for every kind of data, with
            worked examples. The core rule: a decision at time T may use only facts whose{" "}
            <code className="font-mono text-xs">available_at</code> is at or before T.
          </p>
        </AlertDescription>
      </Alert>
    </PlannedPage>
  );
}
