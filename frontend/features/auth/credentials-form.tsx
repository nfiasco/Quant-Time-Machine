"use client";

import Link from "next/link";
import { useActionState } from "react";
import { InfoIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { routes } from "@/config/navigation";
import { signIn, signUp } from "@/features/auth/actions";
import {
  initialAuthFormState,
  PASSWORD_MIN_LENGTH,
  type AuthField,
} from "@/features/auth/validation";

type CredentialsFormProps = { mode: "sign-in" | "sign-up" };

/**
 * Email and password form shared by the sign-in and sign-up pages. Validation runs in
 * the server action, so errors look the same with or without JavaScript.
 */
export function CredentialsForm({ mode }: CredentialsFormProps) {
  const isSignUp = mode === "sign-up";
  const [state, formAction, pending] = useActionState(
    isSignUp ? signUp : signIn,
    initialAuthFormState,
  );
  const errors = state.fieldErrors ?? {};

  // Wires a field to its error message for assistive technology.
  const fieldProps = (field: AuthField) => ({
    id: `${mode}-${field}`,
    name: field,
    "aria-invalid": errors[field] ? true : undefined,
    "aria-describedby": errors[field] ? `${mode}-${field}-error` : undefined,
  });

  return (
    <form action={formAction} noValidate className="flex flex-col gap-6">
      <Alert variant="info">
        <InfoIcon />
        <AlertTitle>Accounts are coming soon</AlertTitle>
        <AlertDescription>
          You can use everything in the app without one. Once sign-in launches, your
          account will keep your experiments and runs.
        </AlertDescription>
      </Alert>

      <FieldGroup>
        <Field data-invalid={errors.email ? true : undefined}>
          <FieldLabel htmlFor={`${mode}-email`}>Email</FieldLabel>
          <Input
            {...fieldProps("email")}
            type="email"
            autoComplete="email"
            required
            defaultValue={state.values?.email}
          />
          <FieldError id={`${mode}-email-error`}>{errors.email}</FieldError>
        </Field>

        <Field data-invalid={errors.password ? true : undefined}>
          <FieldLabel htmlFor={`${mode}-password`}>Password</FieldLabel>
          <Input
            {...fieldProps("password")}
            type="password"
            autoComplete={isSignUp ? "new-password" : "current-password"}
            required
            minLength={isSignUp ? PASSWORD_MIN_LENGTH : undefined}
          />
          {isSignUp && !errors.password ? (
            <FieldDescription className="text-xs">
              At least {PASSWORD_MIN_LENGTH} characters.
            </FieldDescription>
          ) : null}
          <FieldError id={`${mode}-password-error`}>{errors.password}</FieldError>
        </Field>
      </FieldGroup>

      <div className="flex flex-col gap-3">
        <Button type="submit" disabled={pending} className="w-full">
          {pending ? <Spinner data-icon="inline-start" /> : null}
          {isSignUp ? "Create account" : "Sign in"}
        </Button>
        <p role="status" className="min-h-5 text-center text-sm text-muted-foreground">
          {state.status === "unavailable" ? state.message : null}
        </p>
      </div>

      <p className="text-center text-sm text-muted-foreground">
        {isSignUp ? "Already have an account? " : "New here? "}
        <Link
          href={isSignUp ? routes.signIn.href : routes.signUp.href}
          className="rounded-sm font-medium text-foreground underline underline-offset-4"
        >
          {isSignUp ? "Sign in" : "Create an account"}
        </Link>
      </p>
    </form>
  );
}
