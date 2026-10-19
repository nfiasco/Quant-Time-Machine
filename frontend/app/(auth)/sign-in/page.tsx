import { routeMetadata, routes } from "@/config/navigation";
import { CredentialsForm } from "@/features/auth/credentials-form";

export const metadata = routeMetadata(routes.signIn);

export default function SignInPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="text-sm text-muted-foreground">
          Pick up your research where you left off.
        </p>
      </div>
      <CredentialsForm mode="sign-in" />
    </div>
  );
}
