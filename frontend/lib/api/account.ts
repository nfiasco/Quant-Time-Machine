// Server-only through lib/supabase/server's next/headers import. Never send the
// session token to a Client Component or return it in a page's props.
import { ApiError, apiFetch } from "@/lib/api/client";
import type { GetResponse } from "@/lib/api/types";
import { createClient } from "@/lib/supabase/server";

/** Forward the opaque access token; FastAPI verifies it before returning an identity. */
export async function getApiIdentity(verifiedUserId: string): Promise<GetResponse<"/v1/me">> {
  const client = await createClient();
  if (!client) {
    throw new ApiError(503, "/v1/me", {
      error: {
        code: "auth_unavailable",
        message: "Accounts are temporarily unavailable.",
        details: [],
      },
    });
  }
  // getSession is used only to read the opaque token, never to trust its user/claims.
  const { data, error } = await client.auth.getSession();
  if (error || !data.session?.access_token) {
    throw new ApiError(401, "/v1/me", {
      error: { code: "unauthorized", message: "Sign in to continue.", details: [] },
    });
  }
  const identity = await apiFetch<GetResponse<"/v1/me">>("/v1/me", {
    cache: "no-store",
    headers: { Authorization: `Bearer ${data.session.access_token}` },
  });
  if (identity.user_id !== verifiedUserId) {
    throw new ApiError(401, "/v1/me", {
      error: {
        code: "unauthorized",
        message: "Your account could not be verified. Sign out and try again.",
        details: [],
      },
    });
  }
  return identity;
}
