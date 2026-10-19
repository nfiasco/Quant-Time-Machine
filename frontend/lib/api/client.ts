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

/** The API answered with a non-2xx status. `body` is the parsed JSON error, if any. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    readonly body: unknown,
  ) {
    super(`API request to ${path} failed with status ${status}`);
    this.name = "ApiError";
  }
}

export type ApiFetchOptions = RequestInit & {
  /** Abort the request after this many milliseconds. Default: 10 seconds. */
  timeoutMs?: number;
};

/**
 * Fetches a backend path and parses the JSON response. Throws ApiError on a non-2xx
 * status, and the fetch error (network failure, timeout) when the API can't be reached.
 * All backend calls go through this function, usually via a typed wrapper in lib/api/.
 */
export async function apiFetch<T>(
  path: string,
  { timeoutMs = 10_000, headers, signal, ...init }: ApiFetchOptions = {},
): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: { Accept: "application/json", ...headers },
    signal: signal ?? AbortSignal.timeout(timeoutMs),
  });

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    throw new ApiError(response.status, path, body);
  }

  return (await response.json()) as T;
}
