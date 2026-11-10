import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Unit tests for framework-free modules (lib/, and features/*/ files without React).
// Async Server Components can't run under Vitest, so pages are checked in the browser
// (GUIDELINES.md, "Testing").
export default defineConfig({
  resolve: {
    // The same "@/" alias as tsconfig.json's paths.
    alias: [{ find: /^@\//, replacement: fileURLToPath(new URL("./", import.meta.url)) }],
  },
  test: {
    environment: "node",
    include: ["**/*.test.ts"],
    exclude: ["node_modules/**", ".next/**"],
  },
});
