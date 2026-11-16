import { afterEach, expect, it, vi } from "vitest";

import { getSiteUrl, getSupabaseConfig } from "@/lib/supabase/config";

afterEach(() => vi.unstubAllEnvs());

it("accepts the public key and legacy anon key, and rejects secret keys", () => {
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://fixture.supabase.co");
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_fixture");
  expect(getSupabaseConfig()).not.toBeNull();
  const jwt = (role: string) => `header.${Buffer.from(JSON.stringify({ role })).toString("base64url")}.signature`;
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", jwt("anon"));
  expect(getSupabaseConfig()).not.toBeNull();
  for (const key of [jwt("service_role"), "sb_secret_fixture", "", "malformed"]) {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", key);
    expect(getSupabaseConfig()).toBeNull();
  }
});

it("requires a trusted origin for email links in production", () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("SITE_URL", "");
  expect(getSiteUrl()).toBeNull();
  for (const origin of ["http://evil.example", "https://u:p@example.com", "https://example.com/path", "https://example.com?next=evil"]) {
    vi.stubEnv("SITE_URL", origin);
    expect(getSiteUrl()).toBeNull();
  }
  vi.stubEnv("SITE_URL", "https://app.example.com/");
  expect(getSiteUrl()).toBe("https://app.example.com");
});
