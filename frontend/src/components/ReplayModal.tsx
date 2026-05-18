/**
 * ReplayModal.tsx — gold: hand replay modal.
 * Fetches GET /api/hands/:handId/actions and steps through each decision.
 */
import { useState, useEffect } from "react";
import type { HandReplayAction, Card } from "../types";
import { getHandActions } from "../api/client";
import PlayingCard from "./PlayingCard";
import { t } from "../i18n";

interface ReplayModalProps {
  handId: string;
  onClose: () => void;
}

export default function ReplayModal({ handId, onClose }: ReplayModalProps) {
  const [actions, setActions] = useState<HandReplayAction[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getHandActions(handId).then((result) => {
      if (cancelled) return;
      setLoading(false);
      if (result.error) {
        setError(result.error);
      } else {
        setActions(result.data);
        setStep(0);
      }
    });
    return () => { cancelled = true; };
  }, [handId]);

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t("Hand Replay")}
    >
      <div className="bg-chipy-dark rounded-2xl w-full max-w-md p-6 flex flex-col gap-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="font-display text-chip-gold font-bold text-xl">
            {t("Hand Replay")}
          </h2>
          <button
            onClick={onClose}
            className="text-white/60 hover:text-white text-2xl leading-none"
            aria-label={t("Close replay")}
          >
            ×
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div role="status" aria-busy="true" className="text-center py-8">
            <span className="text-chip-gold animate-pulse">{t("Loading replay...")}</span>
          </div>
        )}

        {/* Error */}
        {!loading && error && (
          <div role="alert" className="text-card-red text-center py-4">
            {error}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && actions !== null && actions.length === 0 && (
          <p className="text-white/40 text-center py-4">
            {t("No actions recorded for this hand.")}
          </p>
        )}

        {/* Action replay */}
        {!loading && !error && actions !== null && actions.length > 0 && (
          <>
            {/* Step indicator */}
            <div className="text-xs text-white/40 text-center">
              {t("Step")} {step + 1} {t("of")} {actions.length}
            </div>

            {/* Current action */}
            {(() => {
              const current = actions[step];
              return (
                <div className="flex flex-col gap-3">
                  {/* Hand snapshot */}
                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-white/60 uppercase tracking-wide">
                      {t("Your hand")}
                    </span>
                    <div className="flex flex-row flex-wrap gap-1">
                      {(current.hand_snapshot as (Card | null)[]).map((card, i) => (
                        <PlayingCard key={i} card={card} />
                      ))}
                    </div>
                  </div>

                  {/* Dealer upcard */}
                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-white/60 uppercase tracking-wide">
                      {t("Dealer upcard")}
                    </span>
                    <PlayingCard card={current.dealer_upcard as Card} />
                  </div>

                  {/* Decision */}
                  <div className="flex flex-col gap-1 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="text-white/60">{t("You played:")}</span>
                      <span className="font-bold text-white capitalize">{current.player_guess}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-white/60">{t("Optimal:")}</span>
                      <span className="font-bold text-chip-gold capitalize">{current.optimal_action}</span>
                    </div>
                    <div className={`font-bold ${current.was_correct ? "text-green-400" : "text-card-red"}`}>
                      {current.was_correct ? t("Correct!") : t("Suboptimal")}
                    </div>
                  </div>

                  {/* Chipy explanation */}
                  {current.chipy_explanation && (
                    <p className="text-white/70 text-xs leading-relaxed bg-white/5 p-3 rounded-lg">
                      {current.chipy_explanation}
                    </p>
                  )}
                </div>
              );
            })()}

            {/* Navigation */}
            <div className="flex items-center justify-between gap-2">
              <button
                onClick={() => setStep((s) => Math.max(0, s - 1))}
                disabled={step === 0}
                className="px-4 py-2 bg-white/10 text-white rounded-lg
                  disabled:opacity-40 disabled:cursor-not-allowed
                  hover:bg-white/20 min-h-[44px]"
              >
                {t("← Prev")}
              </button>
              <button
                onClick={() => setStep((s) => Math.min(actions.length - 1, s + 1))}
                disabled={step === actions.length - 1}
                className="px-4 py-2 bg-white/10 text-white rounded-lg
                  disabled:opacity-40 disabled:cursor-not-allowed
                  hover:bg-white/20 min-h-[44px]"
              >
                {t("Next →")}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
