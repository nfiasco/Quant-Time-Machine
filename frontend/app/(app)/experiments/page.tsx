import { PlannedPage } from "@/components/feedback/planned-page";
import { routeMetadata, routes } from "@/config/navigation";
import { requireAccount } from "@/features/auth/session";

export const metadata = routeMetadata(routes.experiments);

export default async function ExperimentsPage() {
  await requireAccount(routes.experiments.href);
  return <PlannedPage route={routes.experiments} />;
}
