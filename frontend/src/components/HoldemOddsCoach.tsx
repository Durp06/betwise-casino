/**
 * HoldemOddsCoach — "Ask Chipy → odds" for multiplayer Hold'em.
 *
 * A compact Chipy panel with one button that fetches the player's live hand
 * odds (POST /api/holdem/tables/{id}/odds, computed only from the caller's own
 * cards + the public board) and shows the shared PokerOddsGraphic.
 */
import { useState } from "react";
import { getHoldemOdds } from "../api/client";
import type { PokerOdds } from "../types";
import { t } from "../i18n";
import Chipy from "./Chipy";
import PokerOddsGraphic from "./PokerOddsGraphic";

interface HoldemOddsCoachProps {
  tableId: string;
  /** True while the player is holding cards in the active hand. */
  enabled: boolean;
}

export default function HoldemOddsCoach({ tableId, enabled }: HoldemOddsCoachProps) {
  const [odds, setOdds] = useState<PokerOdds | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function ask(): Promise<void> {
    setLoading(true);
    setError(null);
    const res = await getHoldemOdds(tableId);
    setLoading(false);
    if (res.error) {
      setError(res.error);
      return;
    }
    setOdds(res.data);
  }

  return (
    <div
      className="w-full max-w-md ink-outline-thick rounded-xl flex flex-col self-center"
      style={{ backgroundColor: "#1A0A00" }}
      data-testid="holdem-odds-coach"
    >
      <div
        className="flex items-center gap-2 px-3 py-2 border-b-[3px] border-ink"
        style={{ backgroundColor: "#D4AC0D" }}
      >
        <Chipy size={40} expression="thinking" animation="idle" pose="rest" />
        <h2 className="font-display text-ink text-lg tracking-wider leading-none flex-1">
          {t("CHIPY")}
        </h2>
        <button
          type="button"
          onClick={() => void ask()}
          disabled={!enabled || loading}
          className="px-2 py-1 text-xs font-ui rounded border-2 border-ink bg-cream text-ink disabled:opacity-40"
          data-testid="holdem-odds-ask"
        >
          {loading ? t("Reading…") : t("Ask Chipy: odds")}
        </button>
      </div>
      <div className="p-3 flex flex-col gap-2 paper-grain" style={{ backgroundColor: "#F5F0E8" }}>
        {error && (
          <div role="alert" className="text-red-700 text-xs bg-red-50 border-2 border-red-700 px-2 py-1 rounded">
            {error}
          </div>
        )}
        {odds ? (
          <PokerOddsGraphic odds={odds} />
        ) : (
          <p className="font-flavor text-ink/60 text-sm italic">
            {enabled
              ? t("Tap 'Ask Chipy' for your live hand odds.")
              : t("Odds appear once you're dealt into a hand.")}
          </p>
        )}
      </div>
    </div>
  );
}
