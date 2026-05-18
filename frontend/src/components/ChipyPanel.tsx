/**
 * ChipyPanel.tsx — AI coaching flow.
 *
 * Contract (tests/ChipyPanel.test.tsx):
 * - Renders Hit / Stand / Double / Split buttons for ALL four actions.
 * - Illegal actions (not in legalActions prop) are rendered but disabled.
 * - Clicking calls streamAdvice(handId, guess, ...).
 * - While streaming: show loading indicator (role="status" + aria-busy).
 * - After stream: show "Confirm <Action>" button.
 */
import { useState, useCallback } from "react";
import type { Action, AdviceResult } from "../types";
import { streamAdvice } from "../api/client";
import { t } from "../i18n";

export interface ChipyPanelProps {
  handId: string;
  legalActions: Action[];
  dealerUpcard: { suit: string; value: string };
  onConfirm: (action: Action) => void;
  /** Optional accuracy display in header (0–1 float) */
  accuracy?: number;
}

const ALL_ACTIONS: Action[] = ["hit", "stand", "double", "split"];

const ACTION_LABELS: Record<Action, string> = {
  hit:    "Hit",
  stand:  "Stand",
  double: "Double",
  split:  "Split",
};

const ACTION_COLORS: Record<Action, string> = {
  hit:    "bg-green-600 hover:bg-green-500 text-white",
  stand:  "bg-blue-600 hover:bg-blue-500 text-white",
  double: "bg-chip-gold hover:bg-yellow-400 text-chipy-dark",
  split:  "bg-purple-600 hover:bg-purple-500 text-white",
};

export default function ChipyPanel({
  handId,
  legalActions,
  onConfirm,
  accuracy,
}: ChipyPanelProps) {
  const [streaming, setStreaming] = useState(false);
  const [message, setMessage] = useState("");
  const [chosenAction, setChosenAction] = useState<Action | null>(null);
  const [result, setResult] = useState<AdviceResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const legalSet = new Set(legalActions);

  const handleGuess = useCallback(
    (action: Action) => {
      setChosenAction(action);
      setStreaming(true);
      setMessage("");
      setResult(null);
      setError(null);

      streamAdvice(
        handId,
        action,
        (chunk: string) => {
          setMessage((prev) => prev + chunk);
        },
        (finalResult: AdviceResult) => {
          setResult(finalResult);
          setStreaming(false);
        },
        (errMsg: string) => {
          setError(errMsg);
          setStreaming(false);
        },
      );
    },
    [handId],
  );

  function handleConfirm(): void {
    if (chosenAction) {
      onConfirm(chosenAction);
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 bg-chipy-dark rounded-xl w-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="font-display text-chip-gold font-bold text-lg">
          {t("Chipy")}
        </span>
        {accuracy !== undefined && (
          <span className="text-xs text-white/60">
            {t("Chipy accuracy:")} {Math.round(accuracy * 100)}%
          </span>
        )}
      </div>

      {/* Guess buttons — always rendered, illegal ones disabled */}
      {!streaming && !result && (
        <div className="flex flex-col gap-2">
          <p className="text-white/70 text-sm">{t("What would you do?")}</p>
          <div className="grid grid-cols-2 gap-2">
            {ALL_ACTIONS.map((action) => {
              const isLegal = legalSet.has(action);
              return (
                <button
                  key={action}
                  onClick={() => handleGuess(action)}
                  disabled={!isLegal}
                  className={`py-3 rounded-lg font-bold text-sm
                    ${ACTION_COLORS[action]}
                    disabled:opacity-40 disabled:cursor-not-allowed
                    active:scale-95 transition-all
                    min-h-[44px]`}
                >
                  {t(ACTION_LABELS[action])}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Loading state while streaming */}
      {streaming && (
        <div
          role="status"
          aria-busy="true"
          aria-live="polite"
          className="flex flex-col gap-2"
        >
          <div className="flex items-center gap-2 text-chip-gold">
            <span className="animate-spin text-lg">⟳</span>
            <span className="text-sm font-medium">{t("Chipy is thinking...")}</span>
          </div>
          {message && (
            <p className="text-white/80 text-sm leading-relaxed">{message}</p>
          )}
        </div>
      )}

      {/* Result state — show explanation + Confirm button */}
      {!streaming && result && chosenAction && (
        <div className="flex flex-col gap-3">
          {/* Explanation text */}
          {message && (
            <p className="text-white/80 text-sm leading-relaxed">{message}</p>
          )}

          {/* Outcome */}
          <div className="flex items-center gap-2">
            {result.was_correct ? (
              <span className="text-green-400 font-bold text-sm">
                {t("Correct!")}
              </span>
            ) : (
              <span className="text-card-red font-bold text-sm">
                {t("Not optimal.")} {t("Best play:")} {t(ACTION_LABELS[result.optimal_action])}
              </span>
            )}
            <span className="text-white/40 text-xs">
              {t("Streak:")} {result.current_streak}
            </span>
          </div>

          {/* Confirm button */}
          <button
            onClick={handleConfirm}
            className="w-full py-3 bg-chip-gold text-chipy-dark font-bold rounded-lg
              hover:bg-yellow-400 active:scale-95 transition-all
              min-h-[44px]"
          >
            {t("Confirm")} {t(ACTION_LABELS[chosenAction])}
          </button>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="flex flex-col gap-2">
          <p role="alert" className="text-card-red text-sm">
            {error}
          </p>
          <button
            onClick={() => {
              setError(null);
              setChosenAction(null);
            }}
            className="text-white/60 text-xs underline text-left"
          >
            {t("Try again")}
          </button>
        </div>
      )}
    </div>
  );
}
