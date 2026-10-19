import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Type-check every <Link href> and router call against the routes in app/,
  // so a renamed or deleted page fails the build instead of shipping a broken link.
  typedRoutes: true,
};

export default nextConfig;
