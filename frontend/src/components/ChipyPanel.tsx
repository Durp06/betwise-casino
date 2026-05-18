/**
 * ChipyPanel.tsx — AI coaching flow.
 *
 * Contract (tests/ChipyPanel.test.tsx):
 * - Renders Hit / Stand / Double / Split buttons for ALL four actions.
 * - Illegal actions (not in legalActions prop) are rendered but disabled.
 * - Clicking calls streamAdvice(handId, guess, ...).
 * - While streaming: show loading indicator (role="status" + aria-busy).
 * - After stream: show "Confirm <Action>" button.
 *
 * Saloon styling: dim corner-booth panel; amber for Chipy's voice, oxblood
 * for "not optimal" outcome.
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
  accuracy?: number;
}

const ALL_ACTIONS: Action[] = ["hit", "stand", "double", "split"];

const ACTION_LABELS: Record<Action, string> = {
  hit:    "Hit",
  stand:  "Stand",
  double: "Double",
  split:  "Split",
};

const ACTION_CLASSES: Record<Action, string> = {
  hit:    "bg-saloon-leather hover:bg-saloon-blood text-saloon-parchment ring-saloon-brass/40",
  stand:  "bg-saloon-night/60 hover:bg-saloon-oak text-saloon-parchment ring-saloon-brass/40",
  double: "bg-saloon-amber hover:bg-saloon-amber/90 text-saloon-ink ring-saloon-brass/60",
  split:  "bg-saloon-wood hover:bg-saloon-oak text-saloon-parchment ring-saloon-brass/40",
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
        (chunk: string) => setMessage((prev) => prev + chunk),
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
    <div className="saloon-panel flex flex-col gap-3 p-5 rounded-t-xl sm:rounded-xl
      w-full ring-1 ring-saloon-brass/40 border-t-2 border-saloon-amber/60">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="text-saloon-amber font-bold text-lg"
            style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}
          >
            {t("Chipy")}
          </span>
          <span className="text-saloon-ash text-xs italic">— the house coach</span>
        </div>
        {accuracy !== undefined && (
          <span className="text-xs text-saloon-ash uppercase tracking-wider">
            {Math.round(accuracy * 100)}% {t("right")}
          </span>
        )}
      </div>

      {/* Guess buttons */}
      {!streaming && !result && (
        <div className="flex flex-col gap-2">
          <p className="text-saloon-parchment/90 text-sm italic">{t("What's your play, partner?")}</p>
          <div className="grid grid-cols-2 gap-2">
            {ALL_ACTIONS.map((action) => {
              const isLegal = legalSet.has(action);
              return (
                <button
                  key={action}
                  onClick={() => handleGuess(action)}
                  disabled={!isLegal}
                  className={`py-3 rounded-md font-semibold text-sm uppercase tracking-wider
                    ring-1 ${ACTION_CLASSES[action]}
                    disabled:opacity-30 disabled:cursor-not-allowed
                    active:scale-[0.98] transition-all
                    min-h-[44px]`}
                >
                  {t(ACTION_LABELS[action])}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Loading state */}
      {streaming && (
        <div role="status" aria-busy="true" aria-live="polite" className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-saloon-amber">
            <span className="text-sm italic">{t("Chipy's thinkin' it over")}</span>
            <span aria-hidden="true">
              <span className="dot" /><span className="dot" /><span className="dot" />
            </span>
          </div>
          {message && (
            <p className="text-saloon-parchment text-sm leading-relaxed italic">{message}</p>
          )}
        </div>
      )}

      {/* Result state */}
      {!streaming && result && chosenAction && (
        <div className="flex flex-col gap-3">
          {message && (
            <p className="text-saloon-parchment text-sm leading-relaxed italic">{message}</p>
          )}

          <div className="flex items-center justify-between text-xs uppercase tracking-wider">
            {result.was_correct ? (
              <span className="text-saloon-amber font-bold">{t("Smart play.")}</span>
            ) : (
              <span className="text-saloon-blood font-bold">
                {t("Off the chart.")} {t("Book says:")} {t(ACTION_LABELS[result.optimal_action])}
              </span>
            )}
            <span
              key={result.current_streak}
              className="text-saloon-amber streak-pulse font-bold tracking-widest"
              aria-label={`Streak ${result.current_streak}`}
            >
              {t("Streak")} · {result.current_streak}
            </span>
          </div>

          <button
            onClick={handleConfirm}
            className="btn-leather w-full py-3 rounded-md font-bold uppercase tracking-widest
              min-h-[44px]"
          >
            {t("Confirm")} {t(ACTION_LABELS[chosenAction])}
          </button>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="flex flex-col gap-2">
          <p role="alert" className="text-saloon-blood text-sm italic">
            {error}
          </p>
          <button
            onClick={() => {
              setError(null);
              setChosenAction(null);
            }}
            className="text-saloon-amber text-xs underline text-left uppercase tracking-wider"
          >
            {t("Try again")}
          </button>
        </div>
      )}
    </div>
  );
}
