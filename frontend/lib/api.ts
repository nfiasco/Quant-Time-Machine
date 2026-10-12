// Base URL of the backend API. Set NEXT_PUBLIC_API_URL in .env.local (see .env.example).
// Next.js inlines NEXT_PUBLIC_ values at build time, but only for a literal
// `process.env.NEXT_PUBLIC_API_URL` access, so this is the one place that reads it.
export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/+$/, "");

/** Full URL for a backend path, for example `apiUrl("/health")`. */
export function apiUrl(path: string): string {
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}
