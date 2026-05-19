/**
 * BettingControls.tsx — chip-click interface (Cuphead pivot).
 *
 * Each denomination is a clickable SVG chip with the Cuphead notch ring.
 * Current bet shown on a felt plaque. "Deal" button is the big gold CTA.
 */
import { useState } from "react";
import { t } from "../i18n";
import { useGameStore } from "../store/gameStore";
import { dealHand } from "../api/client";
import type { Hand } from "../types";

interface BettingControlsProps {
  tableId: string;
  minBet: number;
  maxBet: number;
  chipBalance: number;
  /** Called with the newly-dealt hand so the parent can update its store
   *  immediately instead of waiting 3 s for the next poll. */
  onDealSuccess?: (newHand: Hand | null) => void;
}

const CHIP_DENOMINATIONS = [100, 500, 2500, 10000, 50000] as const;
type Denomination = (typeof CHIP_DENOMINATIONS)[number];

const CHIP_LABELS: Record<Denomination, string> = {
  100:   "$1",
  500:   "$5",
  2500:  "$25",
  10000: "$100",
  50000: "$500",
};

const CHIP_FILL: Record<Denomination, string> = {
  100:   "#F5F0E8",   // white
  500:   "#C0392B",   // red
  2500:  "#1E8449",   // green
  10000: "#1A1A1A",   // black
  50000: "#6C3483",   // purple
};

// Inline chip — small SVG with the notch ring and a denomination label
function ChipSvg({ denom }: { denom: Denomination }) {
  const fill = CHIP_FILL[denom];
  const label = CHIP_LABELS[denom];
  const labelColor = denom === 100 ? "#1A0A00" : "#F5F0E8";

  const notches = [];
  const count = 12;
  const radius = 38;
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * 2 * Math.PI - Math.PI / 2;
    const cx = 50 + Math.cos(angle) * radius;
    const cy = 50 + Math.sin(angle) * radius;
    const rotateDeg = (angle * 180) / Math.PI + 90;
    notches.push(
      <rect
        key={i}
        x={cx - 1.6} y={cy - 3}
        width={3.2} height={6}
        fill="#F5F0E8" stroke="#1A0A00" strokeWidth={0.8}
        transform={`rotate(${rotateDeg} ${cx} ${cy})`}
      />,
    );
  }

  return (
    <svg viewBox="0 0 100 100" width="100%" height="100%">
      <ellipse cx={51.5} cy={53} rx={40} ry={40} fill="#1A0A00" />
      <circle cx={50} cy={50} r={40} fill={fill} stroke="#1A0A00" strokeWidth={3} />
      {notches}
      <circle cx={50} cy={50} r={26} fill={fill} stroke="#1A0A00" strokeWidth={2} />
      <text
        x={50} y={56} textAnchor="middle"
        fontFamily="Lilita One, sans-serif" fontSize={20}
        fill={labelColor} stroke="#1A0A00" strokeWidth={0.5}
      >
        {label}
      </text>
    </svg>
  );
}

export default function BettingControls({
  tableId,
  minBet,
  maxBet,
  chipBalance,
  onDealSuccess,
}: BettingControlsProps) {
  const { betAmount, placeBet, setMyHand } = useGameStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function addChip(denom: Denomination): void {
    placeBet(Math.min(betAmount + denom, maxBet, chipBalance));
  }

  function clearBet(): void {
    placeBet(0);
    setError(null);
  }

  async function handleDeal(): Promise<void> {
    if (betAmount < minBet) {
      setError(t(`Minimum bet is $${(minBet / 100).toFixed(2)}`));
      return;
    }
    if (betAmount > chipBalance) {
      setError(t("Not enough chips, partner."));
      return;
    }
    setError(null);
    setLoading(true);
    const result = await dealHand(tableId, betAmount);
    setLoading(false);
    if (result.error) {
      setError(result.error);
    } else {
      // Optimistic local update so the UI changes the instant the API returns,
      // instead of leaving the user staring at the old outcome banner for the
      // 3 seconds until the next poll lands.
      setMyHand(result.data);
      placeBet(0);
      onDealSuccess?.(result.data);
    }
  }

  return (
    <div className="flex flex-col items-center gap-4 w-full max-w-md mx-auto">
      {/* Chip row */}
      <div className="flex flex-row flex-wrap gap-3 justify-center">
        {CHIP_DENOMINATIONS.map((denom) => (
          <button
            key={denom}
            onClick={() => addChip(denom)}
            disabled={loading || betAmount + denom > chipBalance}
            className="ink-shadow-sm w-14 h-14 sm:w-16 sm:h-16 rounded-full
              disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label={`${t("Add")} ${CHIP_LABELS[denom]}`}
          >
            <ChipSvg denom={denom} />
          </button>
        ))}
      </div>

      {/* Bet plaque */}
      <div
        className="ink-outline rounded-md px-5 py-2 flex items-center gap-3"
        style={{ backgroundColor: "#0D3B1F" }}
      >
        <span className="font-flavor text-cream text-xs uppercase tracking-wider">
          {t("Bet")}
        </span>
        <span className="font-display text-gold-bright text-2xl gold-drop">
          ${(betAmount / 100).toFixed(2)}
        </span>
        {betAmount > 0 && (
          <button
            onClick={clearBet}
            className="font-flavor text-cream text-xs underline ml-1"
          >
            {t("Clear")}
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <p role="alert" className="font-flavor text-action-hit text-sm text-center">
          {error}
        </p>
      )}

      {/* Deal button */}
      <button
        onClick={handleDeal}
        disabled={loading || betAmount === 0}
        className="ink-outline ink-shadow w-full py-3 rounded-md font-display
          text-3xl tracking-wider uppercase
          disabled:opacity-40 disabled:cursor-not-allowed
          min-h-[56px]"
        style={{ backgroundColor: "#F4D03F", color: "#1A0A00" }}
        aria-busy={loading}
      >
        {loading ? t("Dealin'…") : t("Deal")}
      </button>
    </div>
  );
}
