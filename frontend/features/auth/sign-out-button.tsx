"use client";

import { useActionState } from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { signOut } from "@/features/auth/actions";
import { initialAuthFormState } from "@/features/auth/validation";

export function SignOutButton() {
  const [state, action, pending] = useActionState(signOut, initialAuthFormState);
  return (
    <form action={action} className="flex flex-col items-end gap-1">
      <Button type="submit" variant="ghost" size="sm" disabled={pending}>
        {pending ? <Spinner data-icon="inline-start" /> : null}
        Sign out
      </Button>
      {state.message ? <p role="status" className="max-w-52 text-xs text-destructive">{state.message}</p> : null}
    </form>
  );
}
