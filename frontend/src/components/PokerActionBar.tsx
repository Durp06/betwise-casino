/**
 * PokerActionBar.tsx — fold / check / call / raise / all-in buttons.
 *
 * Reads the current hand state to determine legality (e.g. you can't check
 * when facing a bet). On submit, posts to /api/poker/tournaments/{id}/act.
 */
import { useState } from "react";
import type { PokerActionType, PokerHandState, PokerHandSeatState } from "../types";
import { actPoker } from "../api/client";
import { t } from "../i18n";
import BetSizingSlider from "./BetSizingSlider";

interface PokerActionBarProps {
  tournamentId: string;
  hand: PokerHandState;
  yourSeat: PokerHandSeatState;
  onActed?: () => void;
}

export default function PokerActionBar({
  tournamentId,
  hand,
  yourSeat,
  onActed,
}: PokerActionBarProps) {
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
    const result = await actPoker(tournamentId, action, amount);
    setSubmitting(false);
    if (result.error) {
      setError(result.error);
      return;
    }
    onActed?.();
  }

  function handleRaiseConfirm(): void {
    if (raiseAmount === null) {
      void submit("raise", minRaise);
      return;
    }
    void submit("raise", raiseAmount);
  }

  return (
    <div className="flex flex-col gap-2" data-testid="poker-action-bar">
      {error && (
        <div
          role="alert"
          className="text-red-700 text-sm bg-red-50 border-2 border-red-700 px-2 py-1 rounded"
          data-testid="poker-action-error"
        >
          {error}
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        <button
          type="button"
          disabled={submitting}
          onClick={() => void submit("fold", 0)}
          className="px-3 py-2 font-ui text-sm rounded border-2 border-ink bg-red-200 text-ink disabled:opacity-40"
          data-testid="poker-action-fold"
        >
          {t("Fold")}
        </button>

        {canCheck ? (
          <button
            type="button"
            disabled={submitting}
            onClick={() => void submit("check", 0)}
            className="px-3 py-2 font-ui text-sm rounded border-2 border-ink bg-cream text-ink disabled:opacity-40"
            data-testid="poker-action-check"
          >
            {t("Check")}
          </button>
        ) : (
          <button
            type="button"
            disabled={submitting || toCall > stack}
            onClick={() => void submit("call", 0)}
            className="px-3 py-2 font-ui text-sm rounded border-2 border-ink bg-blue-200 text-ink disabled:opacity-40"
            data-testid="poker-action-call"
          >
            {t("Call")} {toCall}
          </button>
        )}

        <button
          type="button"
          disabled={submitting || stack < hand.min_raise_increment}
          onClick={() => setShowSlider(true)}
          className="px-3 py-2 font-ui text-sm rounded border-2 border-ink bg-orange-200 text-ink disabled:opacity-40"
          data-testid="poker-action-raise"
        >
          {t("Raise")}
        </button>

        <button
          type="button"
          disabled={submitting || stack === 0}
          onClick={() => void submit("all_in", 0)}
          className="px-3 py-2 font-ui text-sm rounded border-2 border-ink bg-action-hit text-cream disabled:opacity-40"
          data-testid="poker-action-all_in"
        >
          {t("All-in")}
        </button>
      </div>

      {showSlider && (
        <div className="flex flex-col gap-2 p-2 border-2 border-ink rounded bg-cream/50">
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
              className="px-3 py-1 font-ui text-sm rounded border-2 border-ink bg-orange-300 text-ink disabled:opacity-40"
              data-testid="poker-action-raise-confirm"
            >
              {t("Confirm raise")}
            </button>
            <button
              type="button"
              onClick={() => setShowSlider(false)}
              disabled={submitting}
              className="px-3 py-1 font-ui text-sm rounded border-2 border-ink bg-cream text-ink"
            >
              {t("Cancel")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
