"use client";

import { MoonIcon, SunIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { applyTheme, saveTheme } from "@/lib/theme";

/**
 * Switches between light and dark and remembers the choice. Both icons are rendered
 * and CSS shows the one for the current theme, so server and client HTML always match.
 */
export function ThemeToggle({ className }: { className?: string }) {
  function toggle() {
    const next = document.documentElement.classList.contains("dark")
      ? "light"
      : "dark";
    applyTheme(next);
    saveTheme(next);
  }

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={toggle}
      aria-label="Toggle light or dark theme"
      title="Toggle light or dark theme"
      className={className}
    >
      <SunIcon className="dark:hidden" />
      <MoonIcon className="hidden dark:block" />
    </Button>
  );
}
