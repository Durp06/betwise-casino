/**
 * RetrySpot.tsx — "Retry this spot" drill control.
 *
 * Presents the saved hand + dealer upcard with action buttons (Hit/Stand/Double).
 * On click, POSTs to /api/practice/grade and renders the returned verdict
 * (classification, explanation, EvalBar with action_evs).
 *
 * AC-F-RETRY1.
 */
import { useState } from "react";
import type { Card, PracticeGrade } from "../types";
import { gradePractice } from "../api/client";
import EvalBar from "./EvalBar";
import PlayingCard from "./PlayingCard";
import { t } from "../i18n";

interface RetrySpotProps {
  hand: Card[];
  dealerUpcard: Card;
  onClose?: () => void;
}

export default function RetrySpot({ hand, dealerUpcard, onClose }: RetrySpotProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [grade, setGrade] = useState<PracticeGrade | null>(null);

  const canDouble = hand.length === 2;

  async function handleAction(action: "hit" | "stand" | "double"): Promise<void> {
    setLoading(true);
    setError(null);
    setGrade(null);

    const result = await gradePractice({
      hand,
      dealer_upcard: dealerUpcard,
      action,
    });

    setLoading(false);
    if (result.error) {
      setError(result.error);
    } else {
      setGrade(result.data);
    }
  }

  return (
    <div className="flex flex-col gap-3 bg-white/5 rounded-xl p-3 mt-1">
      {/* Context: hand + dealer upcard */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex flex-col gap-1">
          <span className="text-[10px] text-white/50 uppercase tracking-wide">{t("Your hand")}</span>
          <div className="flex gap-1">
            {hand.map((card, i) => (
              <PlayingCard key={i} card={card} noAnimate />
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] text-white/50 uppercase tracking-wide">{t("Dealer")}</span>
          <PlayingCard card={dealerUpcard} noAnimate />
        </div>
      </div>

      {/* Action buttons */}
      {!grade && !loading && (
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => void handleAction("hit")}
            className="ink-outline px-3 py-1.5 rounded font-ui text-ink text-xs uppercase
              tracking-wider bg-gold-bright hover:bg-gold-dark disabled:opacity-40"
          >
            {t("Hit")}
          </button>
          <button
            onClick={() => void handleAction("stand")}
            className="ink-outline px-3 py-1.5 rounded font-ui text-cream text-xs uppercase
              tracking-wider bg-action-stand hover:opacity-80 disabled:opacity-40"
          >
            {t("Stand")}
          </button>
          {canDouble && (
            <button
              onClick={() => void handleAction("double")}
              className="ink-outline px-3 py-1.5 rounded font-ui text-cream text-xs uppercase
                tracking-wider bg-action-double hover:opacity-80 disabled:opacity-40"
            >
              {t("Double")}
            </button>
          )}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div role="status" aria-busy="true" className="text-xs text-chip-gold animate-pulse py-2">
          {t("Grading...")}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div role="alert" className="text-red-400 text-xs py-2">
          {error}
        </div>
      )}

      {/* Verdict */}
      {grade && (
        <div className="flex flex-col gap-2">
          {/* Render classification + explanation together so both match unique text queries */}
          <p className="text-xs text-white/70 italic font-bold capitalize">
            {grade.classification}
            {grade.explanation ? ` — ${grade.explanation}` : ""}
          </p>
          {grade.optimal_action && (
            <span className="text-xs text-white/60">
              {t("Optimal:")} <span className="font-bold text-white capitalize">{grade.optimal_action}</span>
            </span>
          )}
          <EvalBar actionEvs={grade.action_evs} bestAction={grade.optimal_action} />
          <button
            onClick={() => {
              setGrade(null);
              setError(null);
            }}
            className="self-start text-xs text-white/50 underline hover:text-white"
          >
            {t("Try again")}
          </button>
        </div>
      )}

      {onClose && (
        <button
          onClick={onClose}
          className="self-start text-xs text-white/40 underline hover:text-white/70"
        >
          {t("Close")}
        </button>
      )}
    </div>
  );
}
