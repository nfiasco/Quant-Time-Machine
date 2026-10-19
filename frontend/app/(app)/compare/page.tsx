import { PlannedPage } from "@/components/feedback/planned-page";
import { routeMetadata, routes } from "@/config/navigation";

export const metadata = routeMetadata(routes.compare);

export default function ComparePage() {
  return <PlannedPage route={routes.compare} />;
}
