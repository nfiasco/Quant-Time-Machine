import { cache } from "react";
import { redirect } from "next/navigation";
import type { User } from "@supabase/supabase-js";

import { signInUrl } from "@/features/auth/redirects";
import { createClient } from "@/lib/supabase/server";

export const getAccount = cache(async (): Promise<{ user: User | null; unavailable: boolean }> => {
  const client = await createClient();
  if (!client) return { user: null, unavailable: true };
  try {
    // Verify with Auth; the user object in a cookie/getSession() is untrusted.
    const { data, error } = await client.auth.getUser();
    return {
      user: error ? null : data.user,
      unavailable: !!error && (!error.status || error.status === 429 || error.status >= 500),
    };
  } catch {
    return { user: null, unavailable: true };
  }
});

/** Repeat the check at private pages/actions; Proxy is only the first boundary. */
export async function requireAccount(next: string) {
  const { user } = await getAccount();
  if (!user) redirect(signInUrl(next));
  return user;
}
