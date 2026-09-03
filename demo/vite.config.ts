import path from "path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
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
