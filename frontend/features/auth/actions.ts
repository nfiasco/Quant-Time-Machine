"use server";

import { validateCredentials, type AuthFormState } from "@/features/auth/validation";

// Accounts aren't live yet: S16.1 sets up Supabase and picks the sign-in methods
// (decision D9). Until then these actions validate the form and say so. S16.3 replaces
// the marked lines with Supabase Auth calls and a redirect to the dashboard.

export async function signIn(
  _previous: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const { email, fieldErrors } = validateCredentials(formData, "sign-in");
  if (Object.keys(fieldErrors).length > 0) {
    return { status: "invalid", fieldErrors, values: { email } };
  }

  // S16.3: sign in with Supabase Auth (signInWithPassword) here, then redirect.
  return {
    status: "unavailable",
    message: "You're not signed in: accounts aren't live yet.",
    values: { email },
  };
}

export async function signUp(
  _previous: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const { email, fieldErrors } = validateCredentials(formData, "sign-up");
  if (Object.keys(fieldErrors).length > 0) {
    return { status: "invalid", fieldErrors, values: { email } };
  }

  // S16.3: create the account with Supabase Auth (signUp) here, then redirect.
  return {
    status: "unavailable",
    message: "No account was created: accounts aren't live yet.",
    values: { email },
  };
}
