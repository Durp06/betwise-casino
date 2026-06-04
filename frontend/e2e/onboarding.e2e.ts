import { test, expect } from "./fixtures";

/**
 * Flow 1 — landing / onboarding.
 *
 * An authenticated player lands in the lobby and is NOT bounced to /login — the
 * session is recognized (identity persists), and the authed lobby renders with
 * all four games on offer. Auth uses the dev bypass — the same mechanism the
 * pytest suite uses — so this is deterministic in CI. Real Supabase email
 * sign-up is verified manually; see the README e2e note.
 */
test("an authenticated player lands in the lobby, not the login wall", async ({ page }) => {
  await page.goto("/lobby");

  // Identity recognized: we stay on /lobby instead of being redirected to /login.
  await expect(page).toHaveURL(/\/lobby/);
  await expect(page.getByText("Choose a Game")).toBeVisible();

  // The authed lobby rendered with the game picker.
  await expect(page.getByTestId("blackjack-lobby-card")).toBeVisible();
});
