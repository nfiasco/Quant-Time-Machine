import Link from "next/link";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { routes } from "@/config/navigation";
import { siteConfig } from "@/config/site";

import { LogoMark } from "./logo";

const sectionLink =
  "hidden rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none md:inline-flex";

export function LandingHeader() {
  return (
    <header className="fixed inset-x-0 top-0 z-50 h-14 border-b border-border/60 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-full w-full max-w-6xl items-center gap-2 px-4 sm:px-6 lg:px-8">
        <Link
          href={routes.home.href}
          className="flex min-w-0 items-center gap-2.5 rounded-md text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <LogoMark />
          <span className="truncate text-sm font-semibold tracking-tight max-sm:sr-only">
            {siteConfig.name}
          </span>
        </Link>
        <nav aria-label="Main" className="ml-auto flex items-center gap-1">
          <a href="#features" className={sectionLink}>
            Features
          </a>
          <a href="#api" className={sectionLink}>
            API
          </a>
          <ThemeToggle className="mx-1" />
          <Button asChild variant="ghost" className="hidden sm:inline-flex">
            <Link href={routes.signIn.href}>Sign in</Link>
          </Button>
          <Button asChild>
            <Link href={routes.dashboard.href}>Enter workspace</Link>
          </Button>
        </nav>
      </div>
    </header>
  );
}
