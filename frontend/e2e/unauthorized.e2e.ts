import { test, expect } from "./fixtures";

/**
 * Flow 3 — the unauthorized edge.
 *
 * A protected API request with no (or a bogus) auth token must be rejected, not
 * silently served. We hit the no-bypass backend on :8001 directly so the dev
 * bypass on :8000 can't mask the check — this is the real production auth path
 * (auth.py::get_current_user raises 401 when there's no valid Bearer token).
 */
const NO_BYPASS_API = "http://127.0.0.1:8001";

test("the API rejects a protected request with no auth token", async ({ request }) => {
  const res = await request.get(`${NO_BYPASS_API}/api/users/me`);
  expect(res.status()).toBe(401);
});

test("the API rejects a protected request with a bogus bearer token", async ({ request }) => {
  const res = await request.get(`${NO_BYPASS_API}/api/users/me`, {
    headers: { Authorization: "Bearer not-a-real-jwt" },
  });
  expect(res.status()).toBe(401);
});

test("the public health endpoint stays open without auth", async ({ request }) => {
  // Sanity check the rejection above is auth-specific, not a blanket block.
  const res = await request.get(`${NO_BYPASS_API}/api/health`);
  expect(res.ok()).toBeTruthy();
});
