/**
 * ActionBar.tsx — Hit / Stand / Double / Split action plaques.
 *
 * Per-action colors per the Cuphead palette, thick ink outline, offset
 * solid shadow that compresses on press. Disabled state desaturates.
 */
import { useState } from "react";
import type { Action } from "../types";
import { t } from "../i18n";
import { takeAction, streamAdvice } from "../api/client";
import { useGameStore } from "../store/gameStore";

interface ActionBarProps {
  tableId: string;
  legalActions: Action[];
  isMyTurn: boolean;
  /** ID of the active hand — required to stream Chipy's critique after a play. */
  handId?: string | null;
  onActionSuccess?: () => void;
}

// Split is omitted on purpose: the schema currently has an implicit
// UNIQUE(session_id, user_id) constraint on hands (one hand per user per
// session), so backend POST /action with "split" returns 501. Rendering a
// button that always errors looked broken — see CLAUDE.md "Known limitations."
// Re-add once the (session_id, user_id, hand_index) migration ships.
const ALL_ACTIONS: Action[] = ["hit", "stand", "double"];

const ACTION_LABELS: Record<Action, string> = {
  hit:    "Hit",
  stand:  "Stand",
  double: "Double",
  split:  "Split",
};

const ACTION_BG: Record<Action, string> = {
  hit:    "bg-action-hit",
  stand:  "bg-action-stand",
  double: "bg-action-double",
  split:  "bg-action-split",
};

export default function ActionBar({
  tableId,
  legalActions,
  isMyTurn,
  handId,
  onActionSuccess,
}: ActionBarProps) {
  const [loading, setLoading] = useState<Action | null>(null);
  const [error, setError] = useState<string | null>(null);
  const {
    setMyHand,
    beginChipyStream,
    appendChipyChunk,
    endChipyStream,
    setLastFinishedHandId,
  } = useGameStore();

  const legalSet = new Set(legalActions);

  async function handleAction(action: Action): Promise<void> {
    setError(null);
    setLoading(action);
    const result = await takeAction(tableId, action);
    setLoading(null);
    if (result.error) {
      setError(result.error);
      return;
    }

    // Push the server's updated hand straight into the store so the new card
    // (and any status change) appears instantly instead of waiting up to 3s
    // for the next poll. Users were clicking Hit and seeing nothing move,
    // then clicking Stand by mistake and ending the round prematurely.
    setMyHand(result.data);
    // If the action terminated the hand (bust/blackjack/standing/finished),
    // record its id so Table.tsx knows to show the celebratory outcome banner
    // for THIS hand. Stale finished hands from a prior session won't match.
    if (
      result.data &&
      result.data.status !== "active"
    ) {
      setLastFinishedHandId(result.data.id);
    }
    onActionSuccess?.();

    // Fire Chipy's post-play critique — affirms or corrects with a reason.
    // Streams into the always-visible ChipyCoach panel. Fire-and-forget;
    // failures fall back to a generic message inside the stream itself.
    if (handId) {
      beginChipyStream("post", handId);
      void streamAdvice(
        handId,
        action,
        (chunk) => appendChipyChunk(chunk),
        () => endChipyStream(),
        () => endChipyStream(),
      );
    }
  }

  return (
    <div className="flex flex-col items-center gap-2 w-full">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 w-full">
        {ALL_ACTIONS.map((action) => {
          const isLegal = legalSet.has(action);
          const isDisabled = !isMyTurn || !isLegal || loading !== null;
          const isLoading = loading === action;
          return (
            <button
              key={action}
              onClick={() => handleAction(action)}
              disabled={isDisabled}
              className={`ink-outline ink-shadow py-3 rounded-md font-ui text-cream uppercase
                tracking-wider text-sm sm:text-base ${ACTION_BG[action]}
                disabled:opacity-40 disabled:saturate-50 disabled:cursor-not-allowed
                min-h-[48px]`}
              aria-busy={isLoading}
              aria-label={t(ACTION_LABELS[action])}
            >
              {isLoading ? (
                <span role="status" className="text-xs">…</span>
              ) : (
                t(ACTION_LABELS[action])
              )}
            </button>
          );
        })}
      </div>
      {error && (
        <p role="alert" className="text-action-hit font-flavor text-sm text-center">
          {error}
        </p>
      )}
      {!isMyTurn && (
        <p className="text-cream/60 font-flavor text-xs text-center">
          {t("Waiting for your turn...")}
        </p>
      )}
    </div>
  );
}
