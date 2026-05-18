/**
 * ChipStack.tsx — visual stack of denomination chips for a bet amount.
 * All monetary values are integers (fake cents): $10.00 = 1000.
 */
import { t } from "../i18n";

interface ChipStackProps {
  amount: number; // in fake cents
  className?: string;
}

// Chip denominations in fake cents with display colors
const DENOMINATIONS = [
  { value: 50000, label: "500", color: "bg-purple-700", text: "text-white" },
  { value: 10000, label: "100", color: "bg-gray-900 border border-gray-600", text: "text-white" },
  { value: 2500,  label: "25",  color: "bg-green-600",  text: "text-white" },
  { value: 500,   label: "5",   color: "bg-card-red",   text: "text-white" },
  { value: 100,   label: "1",   color: "bg-white",      text: "text-gray-900" },
] as const;

/** Format fake cents as a dollar string: 1000 → "$10.00" */
function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export default function ChipStack({ amount, className = "" }: ChipStackProps) {
  // Break amount into denomination counts
  const chips: Array<{ denomination: (typeof DENOMINATIONS)[number]; count: number }> = [];
  let remaining = amount;
  for (const denom of DENOMINATIONS) {
    const count = Math.floor(remaining / denom.value);
    if (count > 0) {
      chips.push({ denomination: denom, count });
      remaining -= count * denom.value;
    }
  }

  if (chips.length === 0) {
    return (
      <span className={`text-white/40 text-sm ${className}`}>
        {t("No bet")}
      </span>
    );
  }

  return (
    <div className={`flex flex-col items-center gap-1 ${className}`} aria-label={`${t("Bet")}: ${formatCents(amount)}`}>
      <div className="flex flex-row flex-wrap gap-1 justify-center">
        {chips.map(({ denomination, count }) =>
          Array.from({ length: Math.min(count, 5) }).map((_, i) => (
            <div
              key={`${denomination.value}-${i}`}
              className={`w-10 h-10 rounded-full flex items-center justify-center
                text-xs font-bold shadow-md ${denomination.color} ${denomination.text}
                min-w-[44px] min-h-[44px]`}
              title={`$${(denomination.value / 100).toFixed(0)}`}
            >
              {denomination.label}
            </div>
          ))
        )}
      </div>
      <span className="text-chip-gold text-sm font-bold">{formatCents(amount)}</span>
    </div>
  );
}
