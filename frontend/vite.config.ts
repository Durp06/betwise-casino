/// <reference types="vitest" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Forward /api/* to the deployed backend so `npm run dev` against
    // localhost:5173 can use the live API (and our existing Supabase auth).
    proxy: {
      "/api": {
        target: "https://betwise-casino-production.up.railway.app",
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
