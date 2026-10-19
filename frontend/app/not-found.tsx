import Link from "next/link";
import { CircleDashedIcon } from "lucide-react";

import { Brand } from "@/components/layout/brand";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { routes } from "@/config/navigation";

// Unmatched URLs. Renders inside the root layout only, without the app shell.
export default function NotFound() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-8 px-4 py-16">
      <Link href={routes.dashboard.href} className="rounded-lg">
        <Brand />
      </Link>
      <div className="flex max-w-md flex-col items-center gap-4 text-center">
        <Badge variant="future">
          <CircleDashedIcon data-icon="inline-start" />
          Not yet known
        </Badge>
        <h1 className="text-2xl font-semibold tracking-tight text-balance">
          This page doesn&apos;t exist
        </h1>
        <p className="text-sm text-pretty text-muted-foreground">
          Either the link is wrong, or the page hasn&apos;t been published yet. Nothing
          here was known at this moment.
        </p>
        <Button asChild>
          <Link href={routes.dashboard.href}>Back to the dashboard</Link>
        </Button>
      </div>
    </main>
  );
}
