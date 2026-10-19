import { PlannedPage } from "@/components/feedback/planned-page";
import { routeMetadata, routes } from "@/config/navigation";

export const metadata = routeMetadata(routes.experiments);

export default function ExperimentsPage() {
  return <PlannedPage route={routes.experiments} />;
}
