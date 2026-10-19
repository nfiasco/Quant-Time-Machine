import { PlannedPage } from "@/components/feedback/planned-page";
import { routeMetadata, routes } from "@/config/navigation";

export const metadata = routeMetadata(routes.assistant);

export default function AssistantPage() {
  return <PlannedPage route={routes.assistant} />;
}
