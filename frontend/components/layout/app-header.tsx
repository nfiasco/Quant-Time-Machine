import Link from "next/link";

import { AccountNav } from "@/components/layout/account-nav";
import { Brand } from "@/components/layout/brand";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { routes } from "@/config/navigation";

/** Sticky top bar inside the app shell: sidebar toggle, theme, and account. */
export function AppHeader() {
  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b bg-background/85 px-4 backdrop-blur-sm sm:px-6">
      <SidebarTrigger className="-ml-1.5" />
      {/* The sidebar (and its logo) is a hidden sheet on phones, so show the mark here. */}
      <Link href={routes.dashboard.href} className="rounded-lg md:hidden">
        <Brand markOnly />
      </Link>
      <div className="ml-auto flex items-center gap-1">
        <ThemeToggle />
        <AccountNav />
      </div>
    </header>
  );
}
