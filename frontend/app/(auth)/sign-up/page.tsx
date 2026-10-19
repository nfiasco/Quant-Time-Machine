import Link from "next/link";

import { routeMetadata, routes } from "@/config/navigation";
import { CredentialsForm } from "@/features/auth/credentials-form";

export const metadata = routeMetadata(routes.signUp);

export default function SignUpPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Create an account</h1>
        <p className="text-sm text-muted-foreground">
          Keep your experiments and runs in one place.
        </p>
      </div>
      <CredentialsForm mode="sign-up" />
      <p className="text-center text-xs text-pretty text-muted-foreground">
        The{" "}
        <Link href={routes.privacy.href} className="rounded-sm underline underline-offset-4">
          privacy page
        </Link>{" "}
        explains what an account stores and how to delete it.
      </p>
    </div>
  );
}
