import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/index.tsx"],
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  target: "es2020",
  treeshake: true,
  external: ["react", "react/jsx-runtime", "@glimpse-run/client"],
  esbuildOptions(options) {
    options.jsx = "automatic";
  },
});
