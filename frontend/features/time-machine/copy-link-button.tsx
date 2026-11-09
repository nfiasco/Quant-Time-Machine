"use client";

import { useState } from "react";
import { CheckIcon, LinkIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

type CopyLinkButtonProps = {
  /** The view's path, such as `/time-machine?as_of=…`; the button copies its full URL. */
  href: string;
};

/** Copies a shareable link to the current view. The address bar holds the same link. */
export function CopyLinkButton({ href }: CopyLinkButtonProps) {
  const [result, setResult] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(new URL(href, window.location.origin).toString());
      setResult("copied");
    } catch {
      setResult("failed");
    }
  }

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <Button type="button" variant="outline" size="sm" onClick={copy}>
        {result === "copied" ? (
          <CheckIcon data-icon="inline-start" />
        ) : (
          <LinkIcon data-icon="inline-start" />
        )}
        {result === "copied" ? "Link copied" : "Copy link"}
      </Button>
      <p role="status" className="text-xs text-muted-foreground empty:hidden">
        {result === "failed" ? "Couldn't copy. The address bar holds the same link." : ""}
      </p>
    </div>
  );
}
