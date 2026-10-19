import Link from "next/link";

import { Button } from "@/components/ui/button";
import { routes } from "@/config/navigation";

/**
 * Account links in the app header. Accounts aren't live yet, so this always shows the
 * signed-out state. S16.3: read the Supabase session here and show the account menu
 * (and sign out) when someone is signed in.
 */
export function AccountNav() {
  return (
    <div className="flex items-center gap-1">
      <Button asChild variant="ghost" size="sm">
        <Link href={routes.signIn.href}>Sign in</Link>
      </Button>
      <Button asChild size="sm" className="hidden sm:inline-flex">
        <Link href={routes.signUp.href}>Create account</Link>
      </Button>
    </div>
  );
}
