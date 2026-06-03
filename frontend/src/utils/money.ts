/**
 * money.ts — single source of truth for rendering monetary amounts.
 *
 * All money is stored as integer cents (project convention: $10.00 = 1000).
 * The player thinks in dollars, so we show clean dollar amounts: whole dollars
 * drop the decimals ("$1,000"), thousands are grouped with commas, and cents
 * are shown ONLY when an amount isn't a whole dollar — e.g. a 3:2 blackjack
 * payout on an odd bet ($7.50). This replaces the ad-hoc `$${(c/100).toFixed(2)}`
 * helper that was copy-pasted across Lobby/TableSeats/Profile/Leaderboard/etc.
 */
export function formatMoney(cents: number): string {
  const dollars = cents / 100;
  const isWhole = cents % 100 === 0;
  const formatted = dollars.toLocaleString("en-US", {
    minimumFractionDigits: isWhole ? 0 : 2,
    maximumFractionDigits: isWhole ? 0 : 2,
  });
  return `$${formatted}`;
}
