import { connection } from "next/server";
import { TerminalIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { API_URL } from "@/lib/api/client";
import { getApiHealth } from "@/lib/api/health";
import { cn } from "@/lib/utils";

function StatusDot({ className }: { className: string }) {
  return <span aria-hidden className={cn("size-1.5 rounded-full", className)} />;
}

/**
 * "API online / offline" pill. Checks the backend on every request, so render it
 * inside <Suspense> with <ApiStatusPending /> as the fallback.
 */
export async function ApiStatus() {
  await connection(); // Check at request time, never at build time.
  const health = await getApiHealth();
  const online = health.status === "online";
  const detail = online
    ? `Connected to ${API_URL}`
    : `Couldn't reach ${API_URL} (${health.reason})`;

  return (
    <Badge variant={online ? "positive" : "future"} title={detail}>
      <StatusDot className={online ? "bg-positive" : "bg-future"} />
      {online ? "API online" : "API offline"}
      <span className="sr-only">. {detail}.</span>
    </Badge>
  );
}

export function ApiStatusPending() {
  return (
    <Badge variant="outline" className="text-muted-foreground">
      <StatusDot className="animate-pulse bg-muted-foreground" />
      Checking API…
    </Badge>
  );
}

/** Development only: how to start the backend when it isn't running. */
export async function ApiOfflineHint() {
  if (process.env.NODE_ENV !== "development") return null;
  await connection();
  const health = await getApiHealth();
  if (health.status === "online") return null;

  return (
    <div className="flex items-start gap-1.5 text-xs text-muted-foreground">
      <TerminalIcon className="mt-px size-3.5 shrink-0" aria-hidden />
      <p className="text-pretty">
        The backend isn&apos;t running at <code className="font-mono">{API_URL}</code>.
        Start it with{" "}
        <code className="rounded bg-muted px-1 py-0.5 font-mono">
          cd backend && uv run fastapi dev
        </code>{" "}
        and reload.
      </p>
    </div>
  );
}
