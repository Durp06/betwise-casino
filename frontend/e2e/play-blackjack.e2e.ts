import { test, expect } from "./fixtures";

/**
 * Flow 2 — the main create-and-interact action.
 *
 * Sit at a blackjack table, place a bet, deal a hand, and play it through to a
 * result. Robust to the dealt outcome: a natural blackjack auto-resolves with no
 * turn to act on, so we only Stand when it's genuinely the player's turn. Every
 * outcome (win / lose / push) lands back on the "Place your next bet" prompt.
 */
test("a player can sit, deal a hand, and play it to a result", async ({ page }) => {
  await page.goto("/lobby");

  await page.getByTestId("blackjack-lobby-card").click();
  await expect(page).toHaveURL(/\/blackjack/);

  // Take the first open seat → routed to that table's felt.
  await page.getByRole("button", { name: "Take Seat", exact: true }).first().click();
  await expect(page).toHaveURL(/\/table\//);

  // Place a $100 chip (clears either seeded table's minimum) and deal.
  await page.getByRole("button", { name: "Add $100", exact: true }).click();
  const deal = page.getByRole("button", { name: "Deal", exact: true });
  await expect(deal).toBeEnabled();
  await deal.click();

  // Either the player gets to act, or the hand auto-resolves (natural blackjack).
  const stand = page.getByRole("button", { name: "Stand", exact: true });
  const nextBet = page.getByText("Place your next bet");
  await expect(stand.or(nextBet).first()).toBeVisible({ timeout: 20_000 });

  if ((await stand.isVisible()) && (await stand.isEnabled())) {
    await stand.click();
  }

  // The round resolves and the table returns to the next-bet prompt.
  await expect(nextBet).toBeVisible({ timeout: 20_000 });
});
