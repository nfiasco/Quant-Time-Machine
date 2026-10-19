import Link from "next/link";
import { ArrowLeftIcon, FolderOpenIcon, LockIcon, RotateCcwIcon } from "lucide-react";

import { Brand } from "@/components/layout/brand";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";

const benefits = [
  { icon: FolderOpenIcon, text: "Save experiments and come back to them later." },
  { icon: RotateCcwIcon, text: "Re-run any result against the same data version." },
  { icon: LockIcon, text: "Private by default: only you can see your work." },
];

// Sign-in and sign-up: a brand panel beside the form, without the app shell.
export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid flex-1 lg:grid-cols-2">
      <aside className="hidden flex-col justify-between gap-10 border-r bg-sidebar p-10 lg:flex">
        <Link href={routes.dashboard.href} className="w-fit rounded-lg">
          <Brand />
        </Link>

        <div className="flex max-w-md flex-col gap-8">
          <p className="text-3xl font-semibold tracking-tight text-balance">
            Test ideas with only what was known at the time.
          </p>
          {/* The knowledge horizon in miniature: known, then T, then not yet known. */}
          <div aria-hidden className="flex flex-col gap-2">
            <div className="flex h-2.5 overflow-hidden rounded-full">
              <span className="w-3/5 bg-known/70" />
              <span className="w-0.5 bg-foreground" />
              <span className="flex-1 rounded-r-full border border-l-0 border-dashed border-future/60 bg-hatch-future" />
            </div>
            <div className="flex font-mono text-xs text-muted-foreground">
              <span className="w-3/5">known</span>
              <span>T → not yet known</span>
            </div>
          </div>
          <ul className="flex flex-col gap-3 text-sm text-muted-foreground">
            {benefits.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                  <Icon className="size-4" aria-hidden />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-muted-foreground">{siteConfig.course}</p>
      </aside>

      <div className="flex min-h-svh flex-col">
        <header className="flex items-center gap-2 p-4 sm:p-6">
          <Button asChild variant="ghost" size="sm">
            <Link href={routes.dashboard.href}>
              <ArrowLeftIcon data-icon="inline-start" />
              Back to dashboard
            </Link>
          </Button>
          <ThemeToggle className="ml-auto" />
        </header>
        <main className="flex flex-1 flex-col items-center justify-center gap-8 px-4 pb-16">
          <Link href={routes.dashboard.href} className="rounded-lg lg:hidden">
            <Brand />
          </Link>
          <div className="w-full max-w-sm">{children}</div>
        </main>
      </div>
    </div>
  );
}
