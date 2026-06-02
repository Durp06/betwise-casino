/**
 * PokerChipyCoach.tsx — Chipy panel for Texas Hold'em.
 *
 * Renders:
 * - Reads / Odds mode toggle (persisted to localStorage via the store)
 * - Stream button to fire SSE advice for the current hand
 * - Confidence-tier badge on every coach output (DETERMINISTIC green,
 *   HEURISTIC orange) — the educational core (brief §4.2).
 */
import { useState } from "react";
import { streamPokerAdvice } from "../api/client";
import { useGameStore } from "../store/gameStore";
import { t } from "../i18n";
import Chipy from "./Chipy";

interface PokerChipyCoachProps {
  handId: string | null;
}

function ConfidenceBadge({
  tier,
}: {
  tier: "DETERMINISTIC" | "HEURISTIC" | null;
}) {
  if (tier === null) return null;
  const isDeterministic = tier === "DETERMINISTIC";
  const cls = isDeterministic
    ? "bg-green-200 text-green-900 border-green-800"
    : "bg-orange-200 text-orange-900 border-orange-800";
  return (
    <span
      className={`px-2 py-0.5 text-[10px] uppercase tracking-widest rounded-full border-2 font-ui ${cls}`}
      data-testid={`confidence-tier-${tier}`}
    >
      {t(tier)}
    </span>
  );
}

export default function PokerChipyCoach({ handId }: PokerChipyCoachProps) {
  const {
    pokerCoachMode,
    setPokerCoachMode,
    pokerCoachText,
    pokerCoachStreaming,
    pokerCoachConfidenceTier,
    pokerCoachRecommendedAction,
    beginPokerCoachStream,
    appendPokerCoachChunk,
    endPokerCoachStream,
  } = useGameStore();
  const [error, setError] = useState<string | null>(null);

  async function fetchAdvice(): Promise<void> {
    if (!handId) return;
    setError(null);
    beginPokerCoachStream();
    await streamPokerAdvice(
      handId,
      (chunk) => appendPokerCoachChunk(chunk),
      (final) => {
        const f = (final ?? {}) as {
          confidence_tier?: "DETERMINISTIC" | "HEURISTIC";
          recommended_action?: string | null;
        };
        endPokerCoachStream(
          f.confidence_tier ?? null,
          f.recommended_action ?? null,
        );
      },
      (msg) => {
        setError(msg);
        endPokerCoachStream(null, null);
      },
    );
  }

  const toggleBase =
    "px-3 py-1 rounded-full font-ui text-[10px] uppercase tracking-widest border-2 border-ink disabled:opacity-40 disabled:cursor-not-allowed";
  const toggleActive = "bg-ink text-cream";
  const toggleInactive = "bg-cream text-ink hover:bg-gold-bright";

  return (
    <aside
      className="ink-outline-thick rounded-xl flex flex-col w-full lg:w-72 xl:w-80 self-start"
      style={{ backgroundColor: "#1A0A00" }}
      aria-live="polite"
      data-testid="poker-chipy-coach"
    >
      <header
        className="flex items-center gap-3 px-3 py-2 border-b-[3px] border-ink"
        style={{ backgroundColor: "#D4AC0D" }}
      >
        <Chipy size={48} expression="idle" animation="idle" pose="rest" />
        <div className="flex flex-col leading-tight flex-1 min-w-0">
          <h2 className="font-display text-ink text-xl tracking-wider leading-none">
            CHIPY
          </h2>
          <span className="font-flavor text-ink/80 text-xs italic truncate">
            {pokerCoachStreaming ? t("Thinking…") : t("Click for read")}
          </span>
        </div>
        <div role="group" aria-label={t("Coach mode")} className="flex gap-1">
          <button
            type="button"
            onClick={() => setPokerCoachMode("reads")}
            disabled={pokerCoachStreaming}
            aria-pressed={pokerCoachMode === "reads"}
            className={`${toggleBase} ${pokerCoachMode === "reads" ? toggleActive : toggleInactive}`}
            data-testid="poker-coach-mode-reads"
          >
            {t("Reads")}
          </button>
          <button
            type="button"
            onClick={() => setPokerCoachMode("odds")}
            disabled={pokerCoachStreaming}
            aria-pressed={pokerCoachMode === "odds"}
            className={`${toggleBase} ${pokerCoachMode === "odds" ? toggleActive : toggleInactive}`}
            data-testid="poker-coach-mode-odds"
          >
            {t("Odds")}
          </button>
        </div>
      </header>

      <div
        className="paper-grain p-3 min-h-[140px] flex flex-col gap-2"
        style={{ backgroundColor: "#F5F0E8" }}
      >
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void fetchAdvice()}
            disabled={!handId || pokerCoachStreaming}
            className="px-2 py-1 text-xs font-ui rounded border-2 border-ink bg-gold-bright text-ink disabled:opacity-40"
            data-testid="poker-coach-fetch"
          >
            {pokerCoachStreaming ? t("Streaming…") : t("Ask Chipy")}
          </button>
          <ConfidenceBadge tier={pokerCoachConfidenceTier} />
          {pokerCoachRecommendedAction && (
            <span
              className="text-xs font-ui uppercase tracking-widest text-ink"
              data-testid="poker-coach-recommended"
            >
              {t("Suggests")}: {pokerCoachRecommendedAction}
            </span>
          )}
        </div>
        {error && (
          <div
            role="alert"
            className="text-red-700 text-xs bg-red-50 border-2 border-red-700 px-2 py-1 rounded"
          >
            {error}
          </div>
        )}
        {pokerCoachText ? (
          <p
            className="font-body text-ink text-sm leading-relaxed whitespace-pre-line"
            data-testid="poker-coach-text"
          >
            {pokerCoachText}
          </p>
        ) : (
          <p className="font-flavor text-ink/60 text-sm italic">
            {t("Push 'Ask Chipy' when it's your turn for a read.")}
          </p>
        )}
      </div>
    </aside>
  );
}
