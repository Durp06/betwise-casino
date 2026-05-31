/**
 * SessionReviewModal.tsx — Hand Review modal (Chess.com-style session review).
 *
 * Fetches GET /api/sessions/:sessionId/review on mount and renders:
 *   - Loading state (aria-busy="true") while fetching
 *   - Error state (role="alert") on failure
 *   - Accuracy header, worst-mistake callout, scrollable action list on success
 *   - EvalBar per action when action_evs is present
 *   - What-if line for non-best/non-sharp actions
 *   - Sharp chip (gold) visually distinct from Best chip (green)
 *   - "Retry this spot" button for non-best/non-sharp decisions
 *
 * Classification chips are color-coded per AC-F-REV1/2.
 */
import { useState, useEffect } from "react";
import type { SessionReview, ReviewAction, Classification, Card } from "../types";
import { getSessionReview } from "../api/client";
import PlayingCard from "./PlayingCard";
import EvalBar from "./EvalBar";
import RetrySpot from "./RetrySpot";
import { t } from "../i18n";

interface SessionReviewModalProps {
  sessionId: string;
  handId: string;
  onClose: () => void;
}

// AC-F-REV2 — classification → Tailwind chip classes
// "sharp" gets a gold/amber treatment, visually distinct from "best" (green)
const CLASSIFICATION_CLASS: Record<Classification, string> = {
  best:       "bg-green-500/20 text-green-300",
  good:       "bg-blue-500/20 text-blue-300",
  inaccuracy: "bg-yellow-500/20 text-yellow-300",
  mistake:    "bg-orange-500/20 text-orange-300",
  blunder:    "bg-red-500/20 text-red-300",
  sharp:      "bg-chip-gold/20 text-chip-gold",
};

function ClassificationChip({ cls }: { cls: Classification }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wide ${CLASSIFICATION_CLASS[cls]}`}
    >
      {cls}
    </span>
  );
}

function ActionRow({ action }: { action: ReviewAction }) {
  const [retryOpen, setRetryOpen] = useState(false);

  // Non-best/non-sharp: show what-if line and retry spot
  const isOptimal = action.classification === "best" || action.classification === "sharp";
  const showWhatIf =
    !isOptimal &&
    action.best_action != null &&
    action.best_action !== action.action &&
    action.dealer_bust_pct != null;

  // Filter out null cards from hand_snapshot for RetrySpot
  const nonNullHand = (action.hand_snapshot as (Card | null)[]).filter(
    (c): c is Card => c !== null,
  );

  return (
    <li className="flex flex-col gap-2 py-3 border-b border-white/10 last:border-none">
      <div className="flex items-center gap-2 flex-wrap">
        <ClassificationChip cls={action.classification} />
        <span className="text-xs text-white/60">
          {t("You played:")} <span className="font-bold text-white capitalize">{action.action}</span>
          {" "}/{t("Optimal:")} <span className="font-bold text-chip-gold capitalize">{action.optimal_action}</span>
        </span>
        {action.ev_loss_chips > 0 && (
          <span className="text-xs text-red-300 ml-auto">
            -{t("EV")}: ${(action.ev_loss_chips / 100).toFixed(2)}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex flex-col gap-1">
          <span className="text-[10px] text-white/50 uppercase tracking-wide">{t("Your hand")}</span>
          <div className="flex gap-1">
            {(action.hand_snapshot as (Card | null)[]).map((card, i) => (
              <PlayingCard key={i} card={card} noAnimate />
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] text-white/50 uppercase tracking-wide">{t("Dealer")}</span>
          <PlayingCard card={action.dealer_upcard as Card} noAnimate />
        </div>
      </div>

      {/* EvalBar — when enriched action_evs data is present */}
      {action.action_evs && (
        <EvalBar actionEvs={action.action_evs} bestAction={action.best_action} />
      )}

      {/* What-if line for non-best decisions */}
      {showWhatIf && (
        <p className="text-xs text-white/50 italic bg-white/5 px-2 py-1 rounded">
          {`${t("You")} ${action.action}. ${t("Best was")} ${action.best_action!} — ${t("dealer's")} ${action.dealer_upcard.value} ${t("busts ~")}${Math.round(action.dealer_bust_pct! * 100)}%.`}
        </p>
      )}

      {action.chipy_explanation && (
        <p className="text-white/60 text-xs italic bg-white/5 p-2 rounded-lg leading-relaxed">
          {action.chipy_explanation}
        </p>
      )}

      {/* Retry this spot — for non-best/non-sharp decisions */}
      {!isOptimal && !retryOpen && (
        <button
          onClick={() => setRetryOpen(true)}
          className="self-start text-xs font-ui text-chip-gold underline hover:text-gold-bright"
        >
          {t("Retry this spot")}
        </button>
      )}

      {!isOptimal && retryOpen && (
        <RetrySpot
          hand={nonNullHand}
          dealerUpcard={action.dealer_upcard as Card}
          onClose={() => setRetryOpen(false)}
        />
      )}
    </li>
  );
}

export default function SessionReviewModal({
  sessionId,
  onClose,
}: SessionReviewModalProps) {
  const [review, setReview] = useState<SessionReview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getSessionReview(sessionId).then((result) => {
      if (cancelled) return;
      setLoading(false);
      if (result.error) {
        setError(result.error);
      } else {
        setReview(result.data);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const worstAction =
    review && review.worst_action_id
      ? review.actions.find((a) => a.id === review.worst_action_id) ?? null
      : null;

  return (
    <div
      className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t("Hand Review")}
    >
      <div className="bg-chipy-dark rounded-2xl w-full max-w-lg p-6 flex flex-col gap-4 max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between flex-shrink-0">
          <h2 className="font-display text-chip-gold font-bold text-xl">
            {t("Hand Review")}
          </h2>
          <button
            onClick={onClose}
            className="text-white/60 hover:text-white text-2xl leading-none"
            aria-label={t("Close review")}
          >
            ×
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div role="status" aria-busy="true" className="text-center py-8">
            <span className="text-chip-gold animate-pulse">{t("Loading review...")}</span>
          </div>
        )}

        {/* Error */}
        {!loading && error && (
          <div role="alert" className="text-red-400 text-center py-4">
            {error}
          </div>
        )}

        {/* Success */}
        {!loading && !error && review && (
          <>
            {/* Summary row */}
            <div className="flex items-center gap-4 flex-shrink-0 text-sm">
              <div className="flex flex-col items-center">
                <span className="text-2xl font-bold text-chip-gold">
                  {Math.round(review.accuracy * 100)}%
                </span>
                <span className="text-white/50 text-xs uppercase tracking-wide">{t("Accuracy")}</span>
              </div>
              <div className="flex flex-col items-center">
                <span className="text-xl font-bold text-red-300">
                  ${(review.ev_lost_chips / 100).toFixed(2)}
                </span>
                <span className="text-white/50 text-xs uppercase tracking-wide">{t("EV Lost")}</span>
              </div>
              <div className="flex flex-col items-center">
                <span className="text-xl font-bold text-white">{review.total_actions}</span>
                <span className="text-white/50 text-xs uppercase tracking-wide">{t("Decisions")}</span>
              </div>
              {review.sharp_count != null && review.sharp_count > 0 && (
                <div className="flex flex-col items-center">
                  <span className="text-xl font-bold text-chip-gold">{review.sharp_count}</span>
                  <span className="text-chip-gold text-xs uppercase tracking-wide">{t("Sharp plays")}</span>
                </div>
              )}
            </div>

            {/* Worst-mistake callout */}
            {worstAction && (
              <div className="flex-shrink-0 bg-red-500/10 border border-red-500/30 rounded-xl p-3 flex flex-col gap-2">
                <h3 className="text-xs font-bold text-red-300 uppercase tracking-wide">
                  {t("Worst mistake")}
                </h3>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-white/70">
                    {t("You played:")} <span className="font-bold text-white capitalize">{worstAction.action}</span>
                    {" /"} {t("Optimal:")} <span className="font-bold text-chip-gold capitalize">{worstAction.optimal_action}</span>
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex gap-1">
                    {(worstAction.hand_snapshot as (Card | null)[]).map((card, i) => (
                      <PlayingCard key={i} card={card} noAnimate />
                    ))}
                  </div>
                  <PlayingCard card={worstAction.dealer_upcard as Card} noAnimate />
                </div>
              </div>
            )}

            {/* Actions list */}
            {review.actions.length === 0 ? (
              <p className="text-white/40 text-center py-4">
                {t("No actions recorded for this session.")}
              </p>
            ) : (
              <ul className="overflow-y-auto max-h-[60vh] flex-1">
                {review.actions.map((action) => (
                  <ActionRow key={action.id} action={action} />
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </div>
  );
}
