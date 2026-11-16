"use client";

import type { Route } from "next";
import Link from "next/link";
import { useActionState } from "react";
import { InfoIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { routes } from "@/config/navigation";
import { requestPasswordReset, signIn, signUp, updatePassword } from "@/features/auth/actions";
import { initialAuthFormState, PASSWORD_MIN_LENGTH, type AuthField, type AuthMode } from "@/features/auth/validation";

type CredentialsFormProps = {
  mode: AuthMode;
  available: boolean;
  next: string;
  notice?: string;
};

const actions = { "sign-in": signIn, "sign-up": signUp, "forgot-password": requestPasswordReset, "reset-password": updatePassword };
const labels = { "sign-in": "Sign in", "sign-up": "Create account", "forgot-password": "Send reset link", "reset-password": "Update password" };

/** Native browser validation plus the same checks at the server boundary. */
export function CredentialsForm({ mode, available, next, notice }: CredentialsFormProps) {
  const [state, formAction, pending] = useActionState(actions[mode], initialAuthFormState);
  const errors = state.fieldErrors ?? {};
  const newPassword = mode === "sign-up" || mode === "reset-password";
  const fieldProps = (field: AuthField) => ({
    id: `${mode}-${field}`,
    name: field,
    "aria-invalid": errors[field] ? true : undefined,
    "aria-describedby": errors[field] ? `${mode}-${field}-error` : undefined,
  });

  return (
    <form action={formAction} className="flex flex-col gap-6">
      <input type="hidden" name="next" value={next} />
      {!available ? (
        <Alert variant="info">
          <InfoIcon aria-hidden />
          <AlertTitle>Accounts unavailable</AlertTitle>
          <AlertDescription>Sign-in is temporarily unavailable. You can still explore the public research pages.</AlertDescription>
        </Alert>
      ) : null}
      {notice ? <Alert variant="warning"><AlertDescription>{notice}</AlertDescription></Alert> : null}
      <FieldGroup>
        {mode !== "reset-password" ? (
          <Field data-invalid={errors.email ? true : undefined}>
            <FieldLabel htmlFor={`${mode}-email`}>Email</FieldLabel>
            <Input {...fieldProps("email")} type="email" autoComplete="email" required defaultValue={state.values?.email} />
            <FieldError id={`${mode}-email-error`}>{errors.email}</FieldError>
          </Field>
        ) : null}
        {mode !== "forgot-password" ? (
          <Field data-invalid={errors.password ? true : undefined}>
            <FieldLabel htmlFor={`${mode}-password`}>{mode === "reset-password" ? "New password" : "Password"}</FieldLabel>
            <Input {...fieldProps("password")} type="password" autoComplete={newPassword ? "new-password" : "current-password"} required minLength={newPassword ? PASSWORD_MIN_LENGTH : undefined} />
            {newPassword && !errors.password ? <FieldDescription className="text-xs">At least {PASSWORD_MIN_LENGTH} characters.</FieldDescription> : null}
            <FieldError id={`${mode}-password-error`}>{errors.password}</FieldError>
          </Field>
        ) : null}
      </FieldGroup>
      {mode === "sign-in" ? (
        <Link href={routes.forgotPassword.href} className="self-end rounded-sm text-sm underline underline-offset-4">Forgot password?</Link>
      ) : null}
      <div className="flex flex-col gap-3">
        <Button type="submit" disabled={pending || !available} className="w-full">
          {pending ? <Spinner data-icon="inline-start" /> : null}
          {labels[mode]}
        </Button>
        <p role="status" aria-live="polite" className="min-h-5 text-center text-sm text-muted-foreground">{state.message}</p>
      </div>
      <p className="text-center text-sm text-muted-foreground">
        {mode === "sign-in" ? "New here? " : mode === "sign-up" ? "Already have an account? " : "Remember your password? "}
        <Link
          href={`${mode === "sign-in" ? routes.signUp.href : routes.signIn.href}?next=${encodeURIComponent(next)}` as Route}
          className="rounded-sm font-medium text-foreground underline underline-offset-4"
        >
          {mode === "sign-in" ? "Create an account" : "Sign in"}
        </Link>
      </p>
    </form>
  );
}
