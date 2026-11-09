"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { RotateCcwIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

type RetryButtonProps = {
  label?: string;
};

/**
 * Renders the current page again on the server, for an inline error a Server Component
 * shows (see ErrorState's `actions`). error.tsx boundaries use their own `retry` instead.
 * Carries `data-pending` while it works, like the forms that dim stale content.
 */
export function RetryButton({ label = "Try again" }: RetryButtonProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <Button
      type="button"
      data-pending={isPending ? "" : undefined}
      onClick={() => startTransition(() => router.refresh())}
    >
      {isPending ? (
        <Spinner aria-hidden data-icon="inline-start" />
      ) : (
        <RotateCcwIcon data-icon="inline-start" />
      )}
      {label}
    </Button>
  );
}
