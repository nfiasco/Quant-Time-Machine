import { ShieldCheckIcon } from "lucide-react";

import { PlannedPage } from "@/components/feedback/planned-page";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { routeMetadata, routes } from "@/config/navigation";

export const metadata = routeMetadata(routes.privacy);

export default function PrivacyPage() {
  return (
    <PlannedPage route={routes.privacy}>
      <Alert variant="info">
        <ShieldCheckIcon />
        <AlertTitle>Today, the app stores no personal data</AlertTitle>
        <AlertDescription>
          <p>
            There are no accounts yet. Your theme choice is saved in your browser, and
            whether the sidebar is open in a cookie; neither identifies you. This page
            will be updated before accounts launch.
          </p>
        </AlertDescription>
      </Alert>
    </PlannedPage>
  );
}
