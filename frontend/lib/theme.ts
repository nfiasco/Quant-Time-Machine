// Light/dark theme, applied as a `.dark` class on <html> (the variant globals.css uses).
// The choice is saved in localStorage; with nothing saved, the OS setting wins.

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "qtm-theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

/**
 * Runs in <head> before the first paint (see components/layout/theme-script.tsx),
 * so the page never flashes the wrong theme. Keep it tiny and dependency-free.
 */
export const themeInitScript = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t!=="light"&&t!=="dark"){t=matchMedia("${DARK_QUERY}").matches?"dark":"light"}document.documentElement.classList.toggle("dark",t==="dark")}catch(e){}})()`;

export function getSavedTheme(): Theme | null {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    return saved === "light" || saved === "dark" ? saved : null;
  } catch {
    return null;
  }
}

export function getSystemTheme(): Theme {
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export function saveTheme(theme: Theme) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage can be unavailable (private mode, blocked cookies); the theme still applies.
  }
}

/** Subscribes to OS theme changes. Returns the unsubscribe function. */
export function onSystemThemeChange(callback: () => void): () => void {
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}
