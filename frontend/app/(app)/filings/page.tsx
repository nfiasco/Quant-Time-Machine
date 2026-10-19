import { PlannedPage } from "@/components/feedback/planned-page";
import { routeMetadata, routes } from "@/config/navigation";

export const metadata = routeMetadata(routes.filings);

export default function FilingsPage() {
  return <PlannedPage route={routes.filings} />;
}
