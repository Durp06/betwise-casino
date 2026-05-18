/**
 * BettingControls.tsx — chip denomination buttons + bet display + confirm.
 * Shows loading state while POST /api/tables/:id/deal is in flight.
 * Shows error if bet is invalid or user has insufficient chips.
 */
import { useState } from "react";
import { t } from "../i18n";
import { useGameStore } from "../store/gameStore";
import { dealHand } from "../api/client";

interface BettingControlsProps {
  tableId: string;
  minBet: number;
  maxBet: number;
  chipBalance: number;
  onDealSuccess?: () => void;
}

// Chip denominations in fake cents
const CHIP_DENOMINATIONS = [100, 500, 2500, 10000, 50000] as const;
type Denomination = (typeof CHIP_DENOMINATIONS)[number];

const CHIP_LABELS: Record<Denomination, string> = {
  100:   "$1",
  500:   "$5",
  2500:  "$25",
  10000: "$100",
  50000: "$500",
};

const CHIP_COLORS: Record<Denomination, string> = {
  100:   "bg-white text-gray-900",
  500:   "bg-card-red text-white",
  2500:  "bg-green-600 text-white",
  10000: "bg-gray-900 text-white border border-gray-600",
  50000: "bg-purple-700 text-white",
};

export default function BettingControls({
  tableId,
  minBet,
  maxBet,
  chipBalance,
  onDealSuccess,
}: BettingControlsProps) {
  const { betAmount, placeBet } = useGameStore();
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
      setError(t("Insufficient chips"));
      return;
    }
    setError(null);
    setLoading(true);
    const result = await dealHand(tableId, betAmount);
    setLoading(false);
    if (result.error) {
      setError(result.error);
    } else {
      onDealSuccess?.();
    }
  }

  return (
    <div className="flex flex-col items-center gap-3 w-full max-w-sm mx-auto">
      {/* Chip denomination buttons */}
      <div className="flex flex-row flex-wrap gap-2 justify-center">
        {CHIP_DENOMINATIONS.map((denom) => (
          <button
            key={denom}
            onClick={() => addChip(denom)}
            disabled={loading || betAmount + denom > chipBalance}
            className={`w-12 h-12 rounded-full font-bold text-xs shadow-md
              ${CHIP_COLORS[denom]}
              disabled:opacity-40 disabled:cursor-not-allowed
              hover:scale-110 active:scale-95 transition-transform
              min-w-[44px] min-h-[44px]`}
            aria-label={`${t("Add")} ${CHIP_LABELS[denom]}`}
          >
            {CHIP_LABELS[denom]}
          </button>
        ))}
      </div>

      {/* Current bet display */}
      <div className="flex items-center gap-2">
        <span className="text-white/60 text-sm">{t("Bet:")}</span>
        <span className="text-chip-gold font-bold text-lg">
          ${(betAmount / 100).toFixed(2)}
        </span>
        {betAmount > 0 && (
          <button
            onClick={clearBet}
            className="text-white/40 hover:text-white text-xs underline"
          >
            {t("Clear")}
          </button>
        )}
      </div>

      {/* Error state */}
      {error && (
        <p role="alert" className="text-card-red text-sm text-center">
          {error}
        </p>
      )}

      {/* Confirm bet button */}
      <button
        onClick={handleDeal}
        disabled={loading || betAmount === 0}
        className="w-full py-3 bg-chip-gold text-chipy-dark font-bold rounded-lg
          disabled:opacity-40 disabled:cursor-not-allowed
          hover:bg-yellow-400 active:scale-95 transition-all
          min-h-[44px]"
        aria-busy={loading}
      >
        {loading ? (
          <span role="status">{t("Dealing...")}</span>
        ) : (
          t("Confirm Bet")
        )}
      </button>
    </div>
  );
}
