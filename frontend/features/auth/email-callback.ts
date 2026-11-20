import { NextResponse, type NextRequest } from "next/server";

import { routes } from "@/config/navigation";
import { safeNext } from "@/features/auth/redirects";
import { createClient } from "@/lib/supabase/server";

/** Support the standard PKCE link and token-hash templates, without leaking tokens. */
export async function handleEmailCallback(request: NextRequest, kind: "code" | "token") {
  const params = request.nextUrl.searchParams;
  const recovery =
    params.get("type") === "recovery" || params.get("next") === routes.resetPassword.href;
  const next = recovery ? routes.resetPassword.href : safeNext(params.get("next"));
  let verified = false;
  const client = await createClient();
  if (client) {
    try {
      const code = params.get("code");
      const tokenHash = params.get("token_hash");
      const type = params.get("type");
      if (kind === "code" && code) {
        const { error } = await client.auth.exchangeCodeForSession(code);
        verified = !error;
      } else if (kind === "token" && tokenHash && (type === "signup" || type === "recovery")) {
        const { error } = await client.auth.verifyOtp({ token_hash: tokenHash, type });
        verified = !error;
      }
    } catch {
      // An expired link or provider outage must not establish an account session.
    }
  }
  const failure = recovery ? routes.forgotPassword.href : routes.signIn.href;
  const destination = verified ? next : `${failure}?error=invalid-link`;
  const response = NextResponse.redirect(new URL(destination, request.url), 303);
  response.headers.set("Cache-Control", "private, no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}
