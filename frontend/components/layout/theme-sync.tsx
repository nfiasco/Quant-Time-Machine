"use client";

import { useLayoutEffect } from "react";

import {
  applyTheme,
  getSavedTheme,
  getSystemTheme,
  onSystemThemeChange,
} from "@/lib/theme";

/**
 * Keeps the `.dark` class in sync after hydration. In development, React Strict Mode
 * remounts the page and resets the attributes on <html>, dropping the class the
 * inline script set; this puts it back before paint. It also follows OS theme
 * changes while nothing is saved. Renders nothing.
 */
export function ThemeSync() {
  useLayoutEffect(() => {
    const sync = () => applyTheme(getSavedTheme() ?? getSystemTheme());
    sync();
    return onSystemThemeChange(sync);
  }, []);

  return null;
}
