import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    // The demo links to ../packages/* by path. Resolve them from TypeScript source (their
    // "source" export condition) so no package build is needed, and keep a single React.
    conditions: ["source"],
    dedupe: ["react", "react-dom"],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          codemirror: [
            "@uiw/react-codemirror",
            "@codemirror/language",
            "@codemirror/state",
            "@codemirror/view",
            "@codemirror/lang-python",
            "@codemirror/lang-javascript",
            "@codemirror/lang-java",
            "@codemirror/lang-cpp",
            "@codemirror/lang-go",
          ],
          react: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
});
