/**
 * PokerSetup.tsx — pre-game configuration for a new Texas Hold'em SNG.
 *
 * Fields: bot count (2–7), advice mode (Reads/Odds), buy-in (cents),
 * starting stack (chips). Submit → POST /api/poker/tournaments → navigate
 * to /poker/table/:id.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createPokerTournament } from "../api/client";
import type { PokerAdviceMode } from "../types";
import { t } from "../i18n";

export default function PokerSetup() {
  const navigate = useNavigate();
  const [botCount, setBotCount] = useState(3);
  const [adviceMode, setAdviceMode] = useState<PokerAdviceMode>("odds");
  const [buyInCents, setBuyInCents] = useState(5_000);
  const [startingStack, setStartingStack] = useState(1500);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    const result = await createPokerTournament({
      bot_count: botCount,
      advice_mode: adviceMode,
      buy_in_cents: buyInCents,
      starting_stack_chips: startingStack,
    });
    setSubmitting(false);
    if (result.error || !result.data) {
      setError(result.error ?? "Unknown error");
      return;
    }
    void navigate(`/poker/table/${result.data.id}`);
  }

  return (
    <main className="min-h-screen bg-felt-green text-cream p-6 flex justify-center">
      <form
        onSubmit={onSubmit}
        className="ink-outline-thick rounded-xl bg-cream text-ink p-6 max-w-md w-full flex flex-col gap-4"
        data-testid="poker-setup-form"
      >
        <h1 className="font-display text-3xl tracking-wider">{t("Texas Hold'em — Setup")}</h1>

        <label className="flex flex-col gap-1">
          <span className="font-ui uppercase tracking-widest text-xs">{t("Bot count")}</span>
          <select
            value={botCount}
            onChange={(e) => setBotCount(Number(e.target.value))}
            className="border-2 border-ink rounded px-2 py-1"
            data-testid="poker-setup-bot-count"
          >
            {[2, 3, 4, 5, 6, 7].map((n) => (
              <option key={n} value={n}>
                {n} {t("bots")}
              </option>
            ))}
          </select>
        </label>

        <fieldset className="flex flex-col gap-1">
          <legend className="font-ui uppercase tracking-widest text-xs">{t("Coach mode")}</legend>
          <div className="flex gap-2">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                name="advice-mode"
                value="odds"
                checked={adviceMode === "odds"}
                onChange={() => setAdviceMode("odds")}
                data-testid="poker-setup-mode-odds"
              />
              {t("Odds (deterministic-only)")}
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                name="advice-mode"
                value="reads"
                checked={adviceMode === "reads"}
                onChange={() => setAdviceMode("reads")}
                data-testid="poker-setup-mode-reads"
              />
              {t("Reads (archetype-aware)")}
            </label>
          </div>
        </fieldset>

        <label className="flex flex-col gap-1">
          <span className="font-ui uppercase tracking-widest text-xs">{t("Buy-in (cents)")}</span>
          <input
            type="number"
            min={100}
            step={100}
            value={buyInCents}
            onChange={(e) => setBuyInCents(Number(e.target.value))}
            className="border-2 border-ink rounded px-2 py-1"
            data-testid="poker-setup-buyin"
          />
          <span className="text-xs text-ink/60">
            ${(buyInCents / 100).toFixed(2)} {t("from bankroll")}
          </span>
        </label>

        <label className="flex flex-col gap-1">
          <span className="font-ui uppercase tracking-widest text-xs">
            {t("Starting stack (chips)")}
          </span>
          <input
            type="number"
            min={500}
            step={100}
            value={startingStack}
            onChange={(e) => setStartingStack(Number(e.target.value))}
            className="border-2 border-ink rounded px-2 py-1"
            data-testid="poker-setup-stack"
          />
        </label>

        {error && (
          <div
            role="alert"
            className="text-red-700 text-sm bg-red-50 border-2 border-red-700 px-2 py-1 rounded"
            data-testid="poker-setup-error"
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 font-ui uppercase tracking-widest border-2 border-ink bg-gold-bright text-ink disabled:opacity-40 rounded"
          data-testid="poker-setup-submit"
        >
          {submitting ? t("Buying in…") : t("Buy in & start")}
        </button>
      </form>
    </main>
  );
}
