"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { AuthError } from "@supabase/supabase-js";

import { routes } from "@/config/navigation";
import { safeNext } from "@/features/auth/redirects";
import { validateCredentials, type AuthFormState } from "@/features/auth/validation";
import { getSiteUrl } from "@/lib/supabase/config";
import { createClient } from "@/lib/supabase/server";

const unavailable: AuthFormState = {
  status: "unavailable",
  message: "Accounts are temporarily unavailable. Please try again later.",
};

function failure(error: AuthError, email?: string): AuthFormState {
  if (!error.status || error.status >= 500) return { ...unavailable, values: { email } };
  const messages: Record<string, string> = {
    invalid_credentials: "The email or password is incorrect.",
    email_not_confirmed: "Confirm your email before signing in. Check your inbox for the confirmation link.",
    weak_password: "Choose a stronger password with at least 8 characters.",
    same_password: "Choose a password different from your current password.",
    over_request_rate_limit: "Too many attempts. Wait a moment and try again.",
    over_email_send_rate_limit: "Too many emails requested. Wait a moment and try again.",
    signup_disabled: "New accounts are temporarily unavailable.",
  };
  return {
    status: "error",
    message: error.status === 429 ? messages.over_request_rate_limit :
      messages[error.code ?? ""] ?? "We couldn't complete that request. Check your details and try again.",
    values: { email },
  };
}

export async function signIn(_previous: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const { email, password, fieldErrors } = validateCredentials(formData, "sign-in");
  if (Object.keys(fieldErrors).length) return { status: "invalid", fieldErrors, values: { email } };
  const client = await createClient();
  if (!client) return { ...unavailable, values: { email } };
  try {
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) return failure(error, email);
  } catch {
    return { ...unavailable, values: { email } };
  }
  revalidatePath("/", "layout");
  redirect(safeNext(formData.get("next")));
}

export async function signUp(_previous: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const { email, password, fieldErrors } = validateCredentials(formData, "sign-up");
  if (Object.keys(fieldErrors).length) return { status: "invalid", fieldErrors, values: { email } };
  const client = await createClient();
  const siteUrl = getSiteUrl();
  if (!client || !siteUrl) return { ...unavailable, values: { email } };
  const next = safeNext(formData.get("next"));
  let signedIn = false;
  try {
    const { data, error } = await client.auth.signUp({
      email, password,
      options: { emailRedirectTo: `${siteUrl}/auth/callback?next=${encodeURIComponent(next)}` },
    });
    if (error) return failure(error, email);
    signedIn = !!data.session;
  } catch {
    return { ...unavailable, values: { email } };
  }
  if (signedIn) {
    revalidatePath("/", "layout");
    redirect(next);
  }
  return {
    status: "success",
    message: "Check your inbox. If this address can be registered, you'll receive a link to confirm your email.",
    values: { email },
  };
}

export async function requestPasswordReset(_previous: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const { email, fieldErrors } = validateCredentials(formData, "forgot-password");
  if (Object.keys(fieldErrors).length) return { status: "invalid", fieldErrors, values: { email } };
  const client = await createClient();
  const siteUrl = getSiteUrl();
  if (!client || !siteUrl) return { ...unavailable, values: { email } };
  try {
    const { error } = await client.auth.resetPasswordForEmail(email, {
      redirectTo: `${siteUrl}/auth/callback?next=/reset-password`,
    });
    if (error) return failure(error, email);
  } catch {
    return { ...unavailable, values: { email } };
  }
  return {
    status: "success",
    message: "If an account exists for this address, you'll receive a password reset link. Open it in this browser.",
    values: { email },
  };
}

export async function updatePassword(_previous: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const { password, fieldErrors } = validateCredentials(formData, "reset-password");
  if (Object.keys(fieldErrors).length) return { status: "invalid", fieldErrors };
  const client = await createClient();
  if (!client) return unavailable;
  try {
    const { data, error: userError } = await client.auth.getUser();
    if (userError || !data.user) return { status: "error", message: "Your reset link has expired. Request a new one." };
    const { error } = await client.auth.updateUser({ password });
    if (error) return failure(error);
  } catch {
    return unavailable;
  }
  revalidatePath("/", "layout");
  return { status: "success", message: "Your password has been updated. You can return to the dashboard." };
}

export async function signOut(): Promise<AuthFormState> {
  const client = await createClient();
  if (!client) return unavailable;
  try {
    const { error } = await client.auth.signOut({ scope: "local" });
    if (error) return failure(error);
  } catch {
    return unavailable;
  }
  revalidatePath("/", "layout");
  redirect(routes.signIn.href);
}
