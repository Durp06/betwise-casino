/**
 * ChipStack.tsx — visual stack of chips for a bet amount.
 *
 * Drawn as stacked SVG ellipses (each offset 4 px up from the one below)
 * to suggest physical chip layers. Total value below in display font.
 */
interface ChipStackProps {
  /** Bet amount in cents */
  amount: number;
  className?: string;
}

const CHIP_VALUES = [50000, 10000, 2500, 500, 100] as const;
const CHIP_FILL: Record<number, string> = {
  50000: "#6C3483",
  10000: "#1A1A1A",
  2500:  "#1E8449",
  500:   "#C0392B",
  100:   "#F5F0E8",
};

function breakdown(amount: number): Array<{ denom: number; count: number }> {
  let remaining = amount;
  const out: Array<{ denom: number; count: number }> = [];
  for (const denom of CHIP_VALUES) {
    if (remaining >= denom) {
      const count = Math.floor(remaining / denom);
      out.push({ denom, count });
      remaining -= denom * count;
    }
  }
  return out;
}

export default function ChipStack({ amount, className = "" }: ChipStackProps) {
  const stacks = breakdown(amount);
  const totalChips = stacks.reduce((sum, s) => sum + s.count, 0);
  const maxVisible = 12;
  const chipsToRender = Math.min(totalChips, maxVisible);

  const flat: string[] = [];
  for (const { denom, count } of stacks) {
    for (let i = 0; i < count; i++) flat.push(CHIP_FILL[denom]);
  }
  const visible = flat.slice(0, chipsToRender);

  return (
    <div className={`flex flex-col items-center gap-1 ${className}`}>
      <div className="relative" style={{ width: 56, height: 18 + visible.length * 4 }}>
        {visible.map((fill, i) => {
          const bottom = i * 4;
          return (
            <svg
              key={i}
              viewBox="0 0 100 30"
              width={56}
              height={20}
              style={{
                position: "absolute",
                left: 0,
                bottom,
                filter: "drop-shadow(2px 2px 0 #1A0A00)",
              }}
            >
              <ellipse cx={50} cy={20} rx={42} ry={6} fill="#1A0A00" />
              <ellipse cx={50} cy={15} rx={42} ry={8} fill={fill} stroke="#1A0A00" strokeWidth={3} />
              <ellipse cx={50} cy={12} rx={42} ry={6} fill={fill} stroke="#1A0A00" strokeWidth={2} />
            </svg>
          );
        })}
      </div>
      <span className="font-display text-gold-bright text-base gold-drop">
        ${(amount / 100).toFixed(0)}
      </span>
    </div>
  );
}
