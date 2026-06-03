/**
 * HoldemActionBar.tsx — fold / check / call / raise / all-in for the
 * multiplayer Hold'em table. Same betting-legality math as the solo trainer's
 * PokerActionBar, but posts to /api/holdem/tables/{id}/act.
 */
import { useState } from "react";
import type { HoldemHandSeatState, HoldemHandState, PokerActionType } from "../types";
import { actHoldem } from "../api/client";
import { t } from "../i18n";
import BetSizingSlider from "./BetSizingSlider";

interface HoldemActionBarProps {
  tableId: string;
  hand: HoldemHandState;
  yourSeat: HoldemHandSeatState;
  onActed?: () => void;
}

export default function HoldemActionBar({
  tableId,
  hand,
  yourSeat,
  onActed,
}: HoldemActionBarProps) {
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [raiseAmount, setRaiseAmount] = useState<number | null>(null);
  const [showSlider, setShowSlider] = useState(false);

  const toCall = hand.current_bet_to_match - yourSeat.current_bet;
  const canCheck = toCall === 0;
  const minRaise = hand.current_bet_to_match + hand.min_raise_increment;
  const stack = yourSeat.final_stack;

  async function submit(action: PokerActionType, amount: number): Promise<void> {
    setError(null);
    setSubmitting(true);
    const result = await actHoldem(tableId, action, amount);
    setSubmitting(false);
    if (result.error) {
      setError(result.error);
      return;
    }
    onActed?.();
  }

  function handleRaiseConfirm(): void {
    void submit("raise", raiseAmount ?? minRaise);
  }

  return (
    <div className="flex flex-col gap-2" data-testid="holdem-action-bar">
      {error && (
        <div
          role="alert"
          className="text-red-700 text-sm bg-red-50 ink-outline px-2 py-1 rounded"
          data-testid="holdem-action-error"
        >
          {error}
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <button
          type="button"
          disabled={submitting}
          onClick={() => void submit("fold", 0)}
          className="px-3 py-2 font-ui text-sm rounded ink-outline ink-shadow bg-red-200 text-ink disabled:opacity-40"
          aria-busy={submitting}
          data-testid="holdem-action-fold"
        >
          {submitting ? t("…") : t("Fold")}
        </button>

        {canCheck ? (
          <button
            type="button"
            disabled={submitting}
            onClick={() => void submit("check", 0)}
            className="px-3 py-2 font-ui text-sm rounded ink-outline ink-shadow bg-cream text-ink disabled:opacity-40"
            aria-busy={submitting}
            data-testid="holdem-action-check"
          >
            {submitting ? t("…") : t("Check")}
          </button>
        ) : (
          <button
            type="button"
            disabled={submitting}
            onClick={() => void submit("call", 0)}
            className="px-3 py-2 font-ui text-sm rounded ink-outline ink-shadow bg-blue-200 text-ink disabled:opacity-40"
            aria-busy={submitting}
            data-testid="holdem-action-call"
          >
            {submitting ? t("…") : `${t("Call")} ${Math.min(toCall, stack)}`}
          </button>
        )}

        <button
          type="button"
          disabled={submitting || stack < hand.min_raise_increment || stack <= toCall}
          onClick={() => setShowSlider(true)}
          className="px-3 py-2 font-ui text-sm rounded ink-outline ink-shadow bg-orange-200 text-ink disabled:opacity-40"
          aria-busy={submitting}
          data-testid="holdem-action-raise"
        >
          {submitting ? t("…") : t("Raise")}
        </button>

        <button
          type="button"
          disabled={submitting || stack === 0}
          onClick={() => void submit("all_in", 0)}
          className="px-3 py-2 font-ui text-sm rounded ink-outline ink-shadow bg-action-hit text-cream disabled:opacity-40"
          aria-busy={submitting}
          data-testid="holdem-action-all_in"
        >
          {submitting ? t("…") : t("All-in")}
        </button>
      </div>

      {showSlider && (
        <div className="flex flex-col gap-2 p-2 ink-outline rounded bg-cream/50">
          <BetSizingSlider
            minRaise={minRaise}
            maxRaise={stack + yourSeat.current_bet}
            potSize={hand.pot_total}
            initialValue={Math.min(stack + yourSeat.current_bet, minRaise * 2)}
            onChange={setRaiseAmount}
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleRaiseConfirm}
              disabled={submitting}
              className="px-3 py-1 font-ui text-sm rounded ink-outline ink-shadow bg-orange-300 text-ink disabled:opacity-40"
              aria-busy={submitting}
              data-testid="holdem-action-raise-confirm"
            >
              {submitting ? t("…") : t("Confirm raise")}
            </button>
            <button
              type="button"
              onClick={() => setShowSlider(false)}
              disabled={submitting}
              className="px-3 py-1 font-ui text-sm rounded ink-outline ink-shadow bg-cream text-ink"
            >
              {submitting ? t("…") : t("Cancel")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
