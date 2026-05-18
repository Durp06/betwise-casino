/**
 * ActionBar.tsx — Hit / Stand / Double / Split action buttons.
 * Disabled when not the player's turn or when an action is illegal.
 */
import { useState } from "react";
import type { Action } from "../types";
import { t } from "../i18n";
import { takeAction } from "../api/client";

interface ActionBarProps {
  tableId: string;
  legalActions: Action[];
  isMyTurn: boolean;
  onActionSuccess?: () => void;
}

const ALL_ACTIONS: Action[] = ["hit", "stand", "double", "split"];

const ACTION_LABELS: Record<Action, string> = {
  hit:    "Hit",
  stand:  "Stand",
  double: "Double",
  split:  "Split",
};

const ACTION_COLORS: Record<Action, string> = {
  hit:    "bg-green-600 hover:bg-green-500",
  stand:  "bg-blue-600 hover:bg-blue-500",
  double: "bg-chip-gold hover:bg-yellow-400 text-chipy-dark",
  split:  "bg-purple-600 hover:bg-purple-500",
};

export default function ActionBar({
  tableId,
  legalActions,
  isMyTurn,
  onActionSuccess,
}: ActionBarProps) {
  const [loading, setLoading] = useState<Action | null>(null);
  const [error, setError] = useState<string | null>(null);

  const legalSet = new Set(legalActions);

  async function handleAction(action: Action): Promise<void> {
    setError(null);
    setLoading(action);
    const result = await takeAction(tableId, action);
    setLoading(null);
    if (result.error) {
      setError(result.error);
    } else {
      onActionSuccess?.();
    }
  }

  return (
    <div className="flex flex-col items-center gap-2 w-full">
      <div className="flex flex-row flex-wrap gap-2 justify-center w-full">
        {ALL_ACTIONS.map((action) => {
          const isLegal = legalSet.has(action);
          const isDisabled = !isMyTurn || !isLegal || loading !== null;
          const isLoading = loading === action;
          return (
            <button
              key={action}
              onClick={() => handleAction(action)}
              disabled={isDisabled}
              className={`flex-1 min-w-[80px] py-3 rounded-lg font-bold text-sm text-white
                ${ACTION_COLORS[action]}
                disabled:opacity-40 disabled:cursor-not-allowed
                active:scale-95 transition-all
                min-h-[44px]`}
              aria-busy={isLoading}
              aria-label={t(ACTION_LABELS[action])}
            >
              {isLoading ? (
                <span role="status" className="text-xs">{t("...")}</span>
              ) : (
                t(ACTION_LABELS[action])
              )}
            </button>
          );
        })}
      </div>
      {error && (
        <p role="alert" className="text-card-red text-sm text-center">
          {error}
        </p>
      )}
      {!isMyTurn && (
        <p className="text-white/40 text-xs text-center">
          {t("Waiting for your turn...")}
        </p>
      )}
    </div>
  );
}
