import type { Route } from "next";

import { routes, type AppRoute } from "@/config/navigation";

/** Keep return destinations on this site and outside the authentication routes. */
export function safeNext(value: unknown): Route {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    /[\\\u0000-\u0020]|%(?:2f|5c|0[0-9a-f]|1[0-9a-f])/i.test(value)
  ) {
    return routes.dashboard.href;
  }
  let url: URL;
  try {
    url = new URL(value, "https://app.invalid");
  } catch {
    return routes.dashboard.href;
  }
  if (
    url.origin !== "https://app.invalid" ||
    url.pathname.startsWith("//") ||
    url.pathname.startsWith("/auth/") ||
    ["/sign-in", "/sign-up", "/forgot-password", "/reset-password"].includes(url.pathname)
  ) {
    return routes.dashboard.href;
  }
  return (url.pathname + url.search) as Route;
}

export function requiresAccount(pathname: string): boolean {
  return (
    (Object.values(routes) as AppRoute[]).some(
      (route) =>
        route.requiresAccount && (pathname === route.href || pathname.startsWith(`${route.href}/`)),
    ) || pathname === routes.resetPassword.href
  );
}

export function signInUrl(next: string) {
  return `${routes.signIn.href}?next=${encodeURIComponent(safeNext(next))}` as Route;
}
