/**
 * ActionBar.tsx — Hit / Stand / Double / Split action plaques.
 *
 * Per-action colors per the Cuphead palette, thick ink outline, offset
 * solid shadow that compresses on press. Disabled state desaturates.
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
