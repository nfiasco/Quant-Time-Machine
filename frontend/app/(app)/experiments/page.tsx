import { PlannedPage } from "@/components/feedback/planned-page";
import { ErrorState } from "@/components/feedback/error-state";
import { RetryButton } from "@/components/feedback/retry-button";
import { routeMetadata, routes } from "@/config/navigation";
import { requireAccount } from "@/features/auth/session";
import { getApiIdentity } from "@/lib/api/account";
import { settle } from "@/lib/api/errors";

export const metadata = routeMetadata(routes.experiments);

export default async function ExperimentsPage() {
  const user = await requireAccount(routes.experiments.href);
  const identity = await settle(getApiIdentity(user.id));
  if (!identity.ok) {
    return (
      <ErrorState
        title="Account verification unavailable"
        description={
          identity.failure.kind === "response"
            ? identity.failure.message
            : "We couldn't reach the account service. Please try again."
        }
        actions={<RetryButton />}
      />
    );
  }
  return <PlannedPage route={routes.experiments} />;
}
