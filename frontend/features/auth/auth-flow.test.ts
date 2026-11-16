import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const { jar, redirect } = vi.hoisted(() => ({
  jar: new Map<string, string>(),
  redirect: vi.fn((path: string): never => { throw new Error(`REDIRECT:${path}`); }),
}));
vi.mock("next/headers", () => ({
  cookies: async () => ({
    getAll: () => [...jar].map(([name, value]) => ({ name, value })),
    set: (name: string, value: string) => { if (value) jar.set(name, value); else jar.delete(name); },
  }),
}));
vi.mock("next/navigation", () => ({ redirect }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

import { requestPasswordReset, signIn, signOut, signUp, updatePassword } from "@/features/auth/actions";
import { handleEmailCallback } from "@/features/auth/email-callback";
import { initialAuthFormState } from "@/features/auth/validation";
import { createClient } from "@/lib/supabase/server";
import { updateSession } from "@/lib/supabase/proxy";

const user = { id: "9b2970ba-c2ba-430b-a680-4a741f022cd3", email: "researcher@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {}, created_at: "2026-01-01T00:00:00Z" };
const token = (expires = Math.floor(Date.now() / 1000) + 3600) => {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode({ sub: user.id, exp: expires, aud: "authenticated" })}.test-signature`;
};
const session = () => ({ access_token: token(), refresh_token: "fixture-refresh-token", token_type: "bearer", expires_in: 3600, user });
const form = (values: Record<string, string> = {}) => {
  const data = new FormData();
  Object.entries({ email: user.email, password: "test-password-42", next: "/experiments?view=recent", ...values }).forEach(([key, value]) => data.set(key, value));
  return data;
};
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json", "X-Supabase-Api-Version": "2024-01-01" } });
const request = (path: string) => new NextRequest(`http://localhost:3000${path}`, {
  headers: { cookie: [...jar].map(([name, value]) => `${name}=${value}`).join("; ") },
});

beforeEach(() => {
  jar.clear();
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://fixture.supabase.co");
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_fixture");
  vi.stubEnv("SITE_URL", "http://localhost:3000");
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input : input.url);
    if (url.pathname.endsWith("/token")) return json(session());
    if (url.pathname.endsWith("/user")) return json(user);
    if (url.pathname.endsWith("/logout")) return new Response(null, { status: 204 });
    if (url.pathname.endsWith("/signup")) return json({ user, session: null });
    if (url.pathname.endsWith("/recover")) return json({});
    if (url.pathname.endsWith("/verify")) return json(session());
    throw new Error(`Unexpected auth request: ${init?.method} ${url.pathname}`);
  }));
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("auth smoke flow with the real Supabase SSR client and a synthetic Auth API", () => {
  it("signs in, persists cookies on a fresh request, protects Experiments, and signs out", async () => {
    const signedOut = await updateSession(request("/experiments?view=recent"));
    expect(signedOut.headers.get("location")).toBe("http://localhost:3000/sign-in?next=%2Fexperiments%3Fview%3Drecent");
    await expect(signIn(initialAuthFormState, form())).rejects.toThrow("REDIRECT:/experiments?view=recent");
    expect([...jar.keys()].some((name) => name.includes("auth-token"))).toBe(true);
    // Recreate the client: no process-local session can make this pass.
    const fresh = await createClient();
    expect((await fresh!.auth.getUser()).data.user?.id).toBe(user.id);
    const signedIn = await updateSession(request("/experiments"));
    expect(signedIn.headers.get("location")).toBeNull();
    expect(signedIn.headers.get("cache-control")).toContain("no-store");
    await expect(signOut()).rejects.toThrow("REDIRECT:/sign-in");
    expect(jar.size).toBe(0);
    expect((await updateSession(request("/experiments"))).headers.get("location")).toContain("/sign-in");
  });

  it("rejects invalid credentials at the provider and never returns passwords or raw errors", async () => {
    vi.mocked(fetch).mockResolvedValue(json({ code: "invalid_credentials", msg: "private provider detail" }, 400));
    const state = await signIn(initialAuthFormState, form());
    expect(state).toMatchObject({ status: "error", message: "The email or password is incorrect." });
    expect(JSON.stringify(state)).not.toMatch(/test-password|private provider detail/);
    expect(jar.size).toBe(0);
  });

  it("refreshes expired cookies for both downstream rendering and the browser response", async () => {
    await expect(signIn(initialAuthFormState, form())).rejects.toThrow("REDIRECT:");
    const name = [...jar.keys()].find((name) => name.endsWith("auth-token"))!;
    const saved = JSON.parse(Buffer.from(jar.get(name)!.slice(7), "base64url").toString());
    saved.expires_at = Math.floor(Date.now() / 1000) - 60;
    saved.access_token = token(saved.expires_at);
    jar.set(name, `base64-${Buffer.from(JSON.stringify(saved)).toString("base64url")}`);
    const req = request("/experiments");
    const response = await updateSession(req);
    expect(response.headers.get("location")).toBeNull();
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("grant_type=refresh_token"))).toBe(true);
    const cookie = response.cookies.get(name)!;
    expect(cookie.httpOnly).toBe(true);
    expect(cookie.sameSite).toBe("lax");
    expect(req.cookies.get(name)?.value).toBe(cookie.value);
    expect(response.headers.get("cache-control")).toContain("no-store");
  });

  it("validates forged submissions before making any provider request", async () => {
    const state = await signUp(initialAuthFormState, form({ email: "invalid", password: "short" }));
    expect(state.status).toBe("invalid");
    expect(state.fieldErrors).toHaveProperty("email");
    expect(state.fieldErrors).toHaveProperty("password");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows the unavailable state without configuration and keeps private routes closed", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "");
    expect((await signIn(initialAuthFormState, form())).status).toBe("unavailable");
    expect((await updateSession(request("/experiments"))).headers.get("location")).toContain("/sign-in");
    expect((await updateSession(request("/time-machine"))).headers.get("location")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not trust a cookie when Auth rejects its user", async () => {
    await expect(signIn(initialAuthFormState, form())).rejects.toThrow("REDIRECT:");
    vi.mocked(fetch).mockResolvedValue(json({ code: "bad_jwt", msg: "invalid token" }, 401));
    expect((await updateSession(request("/experiments"))).headers.get("location")).toContain("/sign-in");
  });

  it("requests confirmation without claiming that an unconfirmed user is signed in", async () => {
    const state = await signUp(initialAuthFormState, form());
    expect(state.status).toBe("success");
    expect(state.message).toContain("Check your inbox");
    expect([...jar.keys()].some((name) => name.endsWith("auth-token"))).toBe(false);
    const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).includes("/signup"));
    expect(String(call?.[0])).toContain("redirect_to=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Fcallback");
  });

  it("requests recovery and updates a password only with a verified session", async () => {
    expect((await updatePassword(initialAuthFormState, form())).status).toBe("error");
    const state = await requestPasswordReset(initialAuthFormState, form());
    expect(state.status).toBe("success");
    expect(state.message).toContain("If an account exists");
    const confirmed = await handleEmailCallback(request("/auth/confirm?token_hash=fixture&type=recovery"), "token");
    expect(confirmed.headers.get("location")).toBe("http://localhost:3000/reset-password");
    expect((await updatePassword(initialAuthFormState, form())).status).toBe("success");
  });

  it("rejects incomplete email links without forwarding tokens or external return URLs", async () => {
    const result = await handleEmailCallback(request("/auth/callback?next=https://evil.example&token_hash=secret"), "code");
    expect(result.headers.get("location")).toBe("http://localhost:3000/sign-in?error=invalid-link");
    expect(result.headers.get("referrer-policy")).toBe("no-referrer");
  });

  it("exchanges a recovery PKCE code using the verifier saved in this browser's cookie", async () => {
    await requestPasswordReset(initialAuthFormState, form());
    const result = await handleEmailCallback(request("/auth/callback?code=fixture-code&next=/reset-password"), "code");
    expect(result.headers.get("location")).toBe("http://localhost:3000/reset-password");
    expect([...jar.keys()].some((name) => name.endsWith("auth-token"))).toBe(true);
    const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).includes("grant_type=pkce"));
    const body = JSON.parse(String(call?.[1]?.body));
    expect(body.auth_code).toBe("fixture-code");
    expect(body.code_verifier).toBeTruthy();
  });
});
