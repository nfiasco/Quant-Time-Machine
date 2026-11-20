import { redirect } from "next/navigation";

import { CredentialsForm } from "@/features/auth/credentials-form";
import { safeNext } from "@/features/auth/redirects";
import { getAccount, requireAccount } from "@/features/auth/session";
import type { AuthMode } from "@/features/auth/validation";
import { getSiteUrl, getSupabaseConfig } from "@/lib/supabase/config";

const copy = {
  "sign-in": ["Sign in", "Pick up your research where you left off."],
  "sign-up": ["Create an account", "Sign in to your workspace. Saving experiments is coming soon."],
  "forgot-password": ["Reset your password", "We'll email you a link to choose a new password."],
  "reset-password": ["Choose a new password", "Use at least 8 characters for your new password."],
};

type AuthScreenProps = { mode: AuthMode; next?: unknown; error?: unknown };

export async function AuthScreen({ mode, next: requestedNext, error }: AuthScreenProps) {
  const next = safeNext(requestedNext);
  if (mode === "reset-password") {
    await requireAccount("/reset-password");
  } else if (mode === "sign-in" || mode === "sign-up") {
    const { user } = await getAccount();
    if (user) redirect(next);
  }
  const available =
    !!getSupabaseConfig() && (mode === "sign-in" || mode === "reset-password" || !!getSiteUrl());
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1.5 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">{copy[mode][0]}</h1>
        <p className="text-sm text-muted-foreground">{copy[mode][1]}</p>
      </div>
      <CredentialsForm
        mode={mode}
        available={available}
        next={next}
        notice={
          error === "invalid-link"
            ? "This link is invalid or expired. Request a new link, or sign in if you've already confirmed your email."
            : undefined
        }
      />
    </div>
  );
}
