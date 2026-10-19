import { PlannedPage } from "@/components/feedback/planned-page";
import { routeMetadata, routes } from "@/config/navigation";

export const metadata = routeMetadata(routes.revisions);

export default function RevisionsPage() {
  return <PlannedPage route={routes.revisions} />;
}
