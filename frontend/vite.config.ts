/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Forward /api/* to a backend. VITE_API_PROXY_TARGET overrides at dev time
    // so localhost:5173 → localhost:8000 works for live coding without editing
    // this file. Defaults to the deployed Railway API.
    proxy: {
      "/api": {
        target:
          process.env.VITE_API_PROXY_TARGET ??
          "https://betwise-casino-production.up.railway.app",
        changeOrigin: true,
        secure: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    globals: true,
  },
});
