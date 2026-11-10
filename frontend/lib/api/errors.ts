import { ApiError } from "@/lib/api/client";
import type { V1Error, V1ErrorCode } from "@/lib/api/types";

/** Why an API call returned no data, in a form a Server Component can render. */
export type ApiFailure =
  | {
      kind: "response";
      status: number;
      /** The API's error code, or null when the body isn't a v1 error (a proxy's 502, say). */
      code: V1ErrorCode | null;
      /** A sentence the page can show as is. */
      message: string;
      /** For a 422, one entry per invalid parameter, such as `as_of`. Otherwise empty. */
      details: { field: string; message: string }[];
    }
  | { kind: "timeout" }
  | { kind: "unreachable" };

/** The outcome of an API call that never throws for the API's own failures. */
export type Settled<T> = { ok: true; value: T } | { ok: false; failure: ApiFailure };

/** True when an ApiError's body has the v1 error shape (doc/api-v1.md, "Errors"). */
export function isV1Error(body: unknown): body is V1Error {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const { error } = body as { error: unknown };
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

/**
 * Classifies an error thrown by `apiFetch`: the API answered with an error, it took too
 * long, or it couldn't be reached. Anything else is a bug, so it's rethrown for the
 * nearest error.tsx boundary.
 */
export function toApiFailure(error: unknown): ApiFailure {
  if (error instanceof ApiError) {
    if (isV1Error(error.body)) {
      const { code, message, details } = error.body.error;
      return {
        kind: "response",
        status: error.status,
        code,
        message,
        details: Array.isArray(details) ? details : [],
      };
    }
    return {
      kind: "response",
      status: error.status,
      code: null,
      message: `The API answered with status ${error.status}.`,
      details: [],
    };
  }

  const name =
    typeof error === "object" && error !== null && "name" in error ? error.name : undefined;
  if (name === "TimeoutError" || name === "AbortError") return { kind: "timeout" };
  // fetch rejects with a TypeError when it can't connect (refused, DNS, CORS in a browser).
  if (error instanceof TypeError) return { kind: "unreachable" };

  throw error;
}

/** Awaits an API call and returns its data or why it failed, instead of throwing. */
export async function settle<T>(request: Promise<T>): Promise<Settled<T>> {
  try {
    return { ok: true, value: await request };
  } catch (error) {
    return { ok: false, failure: toApiFailure(error) };
  }
}
