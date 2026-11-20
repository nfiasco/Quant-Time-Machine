import { describe, expect, it } from "vitest";

import { requiresAccount, safeNext } from "@/features/auth/redirects";

describe("return destinations and account boundaries", () => {
  it.each([
    null,
    "https://evil.example",
    "//evil.example",
    "/\\evil.example",
    "/%5cevil.example",
    "/sign-in",
    "/auth/callback",
    "/reset-password",
    "/foo/../sign-up",
    "/foo/..//evil.example",
    "/%2e%2e//evil.example",
  ])("rejects unsafe or recursive return destination %s", (value) => {
    expect(safeNext(value)).toBe("/dashboard");
  });
  it("preserves an internal page and its query", () => {
    expect(safeNext("/experiments?view=recent")).toBe("/experiments?view=recent");
  });
  it("protects account pages and descendants while keeping research public", () => {
    expect(requiresAccount("/experiments")).toBe(true);
    expect(requiresAccount("/experiments/123")).toBe(true);
    expect(requiresAccount("/experiments-public")).toBe(false);
    expect(requiresAccount("/reset-password")).toBe(true);
    for (const path of ["/", "/dashboard", "/time-machine", "/backtests/new", "/privacy"])
      expect(requiresAccount(path)).toBe(false);
  });
});
