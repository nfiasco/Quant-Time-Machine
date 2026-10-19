// Form state and validation for sign-in and sign-up. Kept out of actions.ts because a
// "use server" module may only export async functions.

/** Keep in sync with `minimum_password_length` in supabase/config.toml. */
export const PASSWORD_MIN_LENGTH = 6;

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export type AuthField = "email" | "password";

export type AuthFormState = {
  status: "idle" | "invalid" | "unavailable";
  /** Shown after a submit, for example why nothing happened. */
  message?: string;
  fieldErrors?: Partial<Record<AuthField, string>>;
  /** Echoed back so the email survives a failed submit. Passwords never are. */
  values?: { email?: string };
};

export const initialAuthFormState: AuthFormState = { status: "idle" };

export function validateCredentials(
  formData: FormData,
  mode: "sign-in" | "sign-up",
): { email: string; password: string; fieldErrors: Partial<Record<AuthField, string>> } {
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const fieldErrors: Partial<Record<AuthField, string>> = {};

  if (!email) {
    fieldErrors.email = "Enter your email address.";
  } else if (!EMAIL_PATTERN.test(email)) {
    fieldErrors.email = "Enter a valid email address, like name@example.com.";
  }

  if (!password) {
    fieldErrors.password = mode === "sign-in" ? "Enter your password." : "Choose a password.";
  } else if (mode === "sign-up" && password.length < PASSWORD_MIN_LENGTH) {
    fieldErrors.password = `Use at least ${PASSWORD_MIN_LENGTH} characters.`;
  }

  return { email, password, fieldErrors };
}
