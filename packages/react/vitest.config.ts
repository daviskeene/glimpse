import { defineConfig } from "vitest/config";

export default defineConfig({
  // Resolve @glimpse-run/client from its TypeScript source so tests need no prior build.
  resolve: { conditions: ["source"] },
  test: {
    environment: "jsdom",
    include: ["test/**/*.test.tsx"],
  },
});
