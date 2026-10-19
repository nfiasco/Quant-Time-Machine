import { themeInitScript } from "@/lib/theme";

/**
 * Inline script for the root layout's <head>: applies the saved or OS theme before
 * the browser paints. Must stay a Server Component; React warns about <script>
 * tags rendered by Client Components.
 */
export function ThemeScript() {
  return <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />;
}
