import Link from "next/link";

import { Button } from "@/components/ui/button";
import { routes } from "@/config/navigation";
import { getAccount } from "@/features/auth/session";
import { SignOutButton } from "@/features/auth/sign-out-button";

/** Verified account state is read on every request, including a page reload. */
export async function AccountNav() {
  const { user, unavailable } = await getAccount();
  if (user) {
    return (
      <div className="flex min-w-0 items-center gap-1">
        <span
          className="max-w-32 truncate text-xs text-muted-foreground sm:max-w-56"
          title={user.email}
        >
          <span className="sr-only">Signed in as </span>
          {user.email ?? "Signed in"}
        </span>
        <SignOutButton />
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1">
      {unavailable ? (
        <span className="hidden text-xs text-muted-foreground lg:inline">Accounts unavailable</span>
      ) : null}
      <Button asChild variant="ghost" size="sm">
        <Link href={routes.signIn.href}>Sign in</Link>
      </Button>
      <Button asChild size="sm" className="hidden sm:inline-flex">
        <Link href={routes.signUp.href}>Create account</Link>
      </Button>
    </div>
  );
}
