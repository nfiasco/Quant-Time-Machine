import { API_URL } from "@/lib/api/client";
import type { ApiFailure } from "@/lib/api/errors";

/**
 * What to tell someone when the API didn't do what a backtest page asked: a title, and a
 * sentence on what happened and what to do. The API's own sentence is shown as is.
 */
export function describeFailure(failure: ApiFailure): { title: string; description: string } {
  switch (failure.kind) {
    case "timeout":
      return {
        title: "The research API took too long",
        description: "It didn't answer within 10 seconds. Try again in a moment.",
      };
    case "unreachable":
      return {
        title: "Couldn't reach the research API",
        description:
          process.env.NODE_ENV === "development"
            ? `Nothing answered at ${API_URL}. Start the backend with "cd backend && uv run fastapi dev", then try again.`
            : `Nothing answered at ${API_URL}. Try again in a moment.`,
      };
    case "response":
      if (failure.code === "runs_unavailable") {
        return { title: "The API can't take a run right now", description: failure.message };
      }
      if (failure.status === 422) {
        return { title: "The API can't run this spec", description: failure.message };
      }
      if (failure.status >= 500) {
        return { title: "The research API had a problem", description: failure.message };
      }
      return { title: "The API refused the request", description: failure.message };
  }
}
