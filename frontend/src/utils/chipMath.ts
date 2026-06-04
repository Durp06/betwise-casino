/**
 * chipMath — casino chip denominations + decomposition, shared by ChipStack and
 * ChipFly so a flying bet uses the same colors/denoms as the static stacks.
 * Amounts are integer cents (project convention).
 */
export const CHIP_DENOMS = [50000, 10000, 2500, 500, 100] as const;

export const CHIP_COLOR: Record<number, string> = {
  100: "#F5F0E8", // white
  500: "#C0392B", // red
  2500: "#1E8449", // green
  10000: "#1A1A1A", // black
  50000: "#6C3483", // purple
};

/**
 * Decompose an amount (cents) into up to `max` representative chips, highest
 * denomination first. Used for the small flying chip stack on a bet.
 */
export function chipBreakdown(cents: number, max = 4): number[] {
  const chips: number[] = [];
  let rem = Math.max(0, Math.round(cents));
  for (const d of CHIP_DENOMS) {
    while (rem >= d && chips.length < max) {
      chips.push(d);
      rem -= d;
    }
  }
  if (chips.length === 0 && cents > 0) chips.push(100);
  return chips;
}
