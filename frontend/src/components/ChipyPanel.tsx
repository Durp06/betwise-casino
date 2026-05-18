/**
 * ChipyPanel.tsx — Chipy coaching flow (rubber-hose pivot).
 *
 * Contract (tests/ChipyPanel.test.tsx):
 * - Renders Hit / Stand / Double / Split buttons for ALL four actions.
 * - Illegal actions disabled but still rendered.
 * - Clicking calls streamAdvice(handId, guess, ...).
 * - While streaming: role="status" + aria-busy.
 * - After stream: shows a "Confirm <Action>" button.
 */
import { useState, useCallback } from "react";
import type { Action, AdviceResult } from "../types";
import { streamAdvice } from "../api/client";
import { t } from "../i18n";
import Chipy from "./Chipy";

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

const ACTION_BG: Record<Action, string> = {
  hit:    "bg-action-hit",
  stand:  "bg-action-stand",
  double: "bg-action-double",
  split:  "bg-action-split",
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
    if (chosenAction) onConfirm(chosenAction);
  }

  // Chipy expression based on flow state
  let expression: "idle" | "thinking" | "happy" | "surprised" = "idle";
  let animation: "idle" | "think" | "bounce" | "shake" | "none" = "idle";
  let pose: "rest" | "wave" | "thumbsup" | "point" = "rest";

  if (streaming) {
    expression = "thinking";
    animation = "think";
  } else if (result?.was_correct) {
    expression = "happy";
    animation = "bounce";
    pose = "thumbsup";
  } else if (result && !result.was_correct) {
    expression = "surprised";
    animation = "shake";
    pose = "point";
  } else if (!result && !streaming) {
    expression = "idle";
    animation = "idle";
    pose = "wave";
  }

  return (
    <div
      className="ink-outline-thick rounded-xl w-full max-w-md slide-up"
      style={{ backgroundColor: "#1A0A00", boxShadow: "8px 8px 0 0 #1A0A00" }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-3 px-4 py-3 border-b-[4px]"
        style={{ borderColor: "#1A0A00", backgroundColor: "#D4AC0D" }}
      >
        <Chipy size={64} expression={expression} animation={animation} pose={pose} />
        <h2 className="font-display text-ink text-3xl tracking-wider">CHIPY</h2>
        {accuracy !== undefined && (
          <span className="ml-auto font-ui text-ink text-xs">
            {Math.round(accuracy * 100)}% {t("right")}
          </span>
        )}
      </div>

      {/* Body */}
      <div
        className="paper-grain p-4 flex flex-col gap-3"
        style={{ backgroundColor: "#F5F0E8" }}
      >
        {/* Guess buttons */}
        {!streaming && !result && (
          <>
            <p className="font-body text-ink text-base text-center">
              {t("What's your move?")}
            </p>
            <div className="grid grid-cols-2 gap-2">
              {ALL_ACTIONS.map((action) => {
                const isLegal = legalSet.has(action);
                return (
                  <button
                    key={action}
                    onClick={() => handleGuess(action)}
                    disabled={!isLegal}
                    className={`ink-outline ink-shadow-sm py-3 rounded-md font-ui
                      text-cream uppercase tracking-wider text-sm
                      ${ACTION_BG[action]}
                      disabled:opacity-40 disabled:saturate-50 disabled:cursor-not-allowed
                      min-h-[44px]`}
                  >
                    {t(ACTION_LABELS[action])}
                  </button>
                );
              })}
            </div>
          </>
        )}

        {/* Loading state */}
        {streaming && (
          <div role="status" aria-busy="true" aria-live="polite" className="flex flex-col gap-2">
            <p className="font-flavor text-ink text-sm italic">
              {t("Chipy's thinkin' it over…")}
            </p>
            {message && (
              <p className="font-body text-ink text-base leading-relaxed">{message}</p>
            )}
          </div>
        )}

        {/* Result state */}
        {!streaming && result && chosenAction && (
          <div className="flex flex-col gap-3">
            {message && (
              <p className="font-body text-ink text-base leading-relaxed">{message}</p>
            )}

            <div className="flex items-center justify-between font-ui uppercase tracking-wider text-xs">
              {result.was_correct ? (
                <span className="text-action-stand font-bold">
                  {t("Smart play!")}
                </span>
              ) : (
                <span className="text-action-hit font-bold">
                  {t("Off the chart.")} {t("Best:")} {t(ACTION_LABELS[result.optimal_action])}
                </span>
              )}
              <span
                key={result.current_streak}
                className="text-gold-dark"
                aria-label={`Streak ${result.current_streak}`}
              >
                {t("Streak")} · {result.current_streak}
              </span>
            </div>

            <button
              onClick={handleConfirm}
              className="ink-outline ink-shadow w-full py-3 rounded-md font-ui
                text-cream uppercase tracking-wider bg-gold-mid
                min-h-[48px]"
              style={{ color: "#1A0A00" }}
            >
              {t("Confirm")} {t(ACTION_LABELS[chosenAction])}
            </button>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="flex flex-col gap-2">
            <p role="alert" className="font-flavor text-action-hit text-sm italic">
              {error}
            </p>
            <button
              onClick={() => {
                setError(null);
                setChosenAction(null);
              }}
              className="font-ui text-action-double text-xs underline self-start uppercase"
            >
              {t("Try again")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
