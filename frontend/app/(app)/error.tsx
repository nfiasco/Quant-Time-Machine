"use client"; // Error boundaries must be Client Components.

import { useEffect } from "react";

import { ErrorState } from "@/components/feedback/error-state";

export default function SegmentError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <ErrorState
      title="This page didn't load"
      description="Something went wrong while rendering it. Try again, or go back to the dashboard."
      digest={error.digest}
      onRetry={retry}
    />
  );
}
