import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e config — the gold "pick one" end-to-end suite.
 *
 * Topology (the webServer array spins all of it up with one `playwright test`):
 *   - uvicorn :8000  backend WITH the BETWISE_DEV_USER_ID bypass over a freshly
 *     seeded SQLite DB (backend.dev_seed). This is the API the UI talks to.
 *   - vite dev :5173 frontend with the matching VITE_DEV_USER_ID auth bypass and
 *     /api proxied to :8000. `import.meta.env.DEV` is true under `vite dev`, so
 *     the frontend bypass is active here and ONLY here — a production
 *     `vite build` never enables it.
 *   - uvicorn :8001  backend WITHOUT the bypass, used only by the unauthorized
 *     spec to prove a no-token request is rejected with 401 (the dev bypass on
 *     :8000 would otherwise mask that check).
 *
 * No production source changes are needed: both auth bypasses already exist for
 * local dev and are gated so they can never activate in a prod build/deploy. The
 * suite exercises the real React app + real FastAPI + real DB through a browser,
 * with auth stubbed exactly the way the pytest suite already stubs it.
 */
const DEV_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
const SQLITE_URL = "sqlite+aiosqlite:///./e2e.sqlite";
// Override locally (e.g. E2E_PYTHON=/path/to/.venv/Scripts/python.exe) when the
// venv python isn't on PATH; CI uses the actions/setup-python `python`.
const PYTHON = process.env.E2E_PYTHON ?? "python";
const isCI = !!process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: false,
  forbidOnly: isCI,
  retries: isCI ? 2 : 0,
  workers: 1,
  reporter: isCI ? [["list"], ["html", { open: "never" }]] : "list",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
    video: "off",
    // The app wraps everything in <MotionConfig reducedMotion="user">, so
    // emulating reduced-motion disables framer-motion's transform animations.
    // (Raw CSS animations are killed separately in e2e/fixtures.ts.)
    reducedMotion: "reduce",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      // Backend WITH dev bypass + freshly-seeded SQLite schema (idempotent seed).
      command: `${PYTHON} -m backend.dev_seed && ${PYTHON} -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`,
      cwd: "..",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        BETWISE_TEST_DB_URL: SQLITE_URL,
        BETWISE_DEV_USER_ID: DEV_USER_ID,
      },
    },
    {
      // Backend WITHOUT bypass — only the unauthorized (401) spec talks to it.
      command: `${PYTHON} -m uvicorn backend.main:app --host 127.0.0.1 --port 8001`,
      cwd: "..",
      url: "http://127.0.0.1:8001/api/health",
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        BETWISE_TEST_DB_URL: SQLITE_URL,
      },
    },
    {
      // Frontend dev server: matching auth bypass + /api proxy to the :8000 API.
      command: "npm run dev -- --port 5173 --strictPort --host 127.0.0.1",
      cwd: ".",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !isCI,
      timeout: 120_000,
      env: {
        VITE_DEV_USER_ID: DEV_USER_ID,
        VITE_API_PROXY_TARGET: "http://127.0.0.1:8000",
      },
    },
  ],
});
