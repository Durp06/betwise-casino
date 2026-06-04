/**
 * BlackjackOddsGraphic — Chipy's odds readout for blackjack: the dealer's bust
 * chance for the shown upcard + the expected value of each legal play, with the
 * best play flagged. Purely presentational.
 */
import type { CSSProperties } from "react";
import { motion } from "framer-motion";
import type { BlackjackOdds } from "../types";
import { t } from "../i18n";

function pctStr(x: number): string {
  return `${Math.round(Math.max(0, Math.min(1, x)) * 100)}%`;
}
function evStr(x: number): string {
  return `${x >= 0 ? "+" : ""}${x.toFixed(2)}`;
}
// EV (roughly -1..+1) → a bar growing from the center line.
function evBarStyle(ev: number): CSSProperties {
  const mag = Math.min(Math.abs(ev), 1) * 50;
  return ev >= 0 ? { left: "50%", width: `${mag}%` } : { right: "50%", width: `${mag}%` };
}

export default function BlackjackOddsGraphic({ odds }: { odds: BlackjackOdds | null }) {
  if (!odds) return null;
  const ACTION_LABEL: Record<string, string> = {
    stand: t("Stand"),
    hit: t("Hit"),
    double: t("Double"),
  };

  return (
    <motion.div
      data-testid="blackjack-odds-graphic"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="ink-outline rounded-lg p-3 flex flex-col gap-2 bg-cream text-ink"
    >
      <div className="flex items-baseline justify-between">
        <span className="font-ui uppercase tracking-widest text-[10px] text-ink/70">{t("Hand odds")}</span>
        <span className="font-ui text-[10px] text-ink/60">
          {t("You have")} {odds.player_total}
          {odds.player_is_soft ? ` ${t("(soft)")}` : ""}
        </span>
      </div>

      {/* Dealer bust chance */}
      <div className="flex items-end gap-2">
        <span className="font-display text-2xl leading-none text-action-hit" data-testid="dealer-bust-pct">
          {pctStr(odds.dealer_bust_pct)}
        </span>
        <span className="font-flavor italic text-xs text-ink/60 mb-0.5">{t("dealer bust chance")}</span>
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full border-2 border-ink" aria-hidden="true">
        <div className="h-full bg-action-hit" style={{ width: pctStr(odds.dealer_bust_pct) }} />
      </div>

      {/* Per-action EV */}
      <div className="flex flex-col gap-1 mt-1">
        <span className="font-ui uppercase tracking-widest text-[10px] text-ink/70">{t("Expected value")}</span>
        {odds.actions.map((a) => {
          const best = a.action === odds.best_action;
          const positive = a.ev >= 0;
          return (
            <div key={a.action} className="flex items-center gap-2">
              <span className={`w-12 text-[11px] font-ui uppercase ${best ? "font-bold text-ink" : "text-ink/70"}`}>
                {ACTION_LABEL[a.action] ?? a.action}
              </span>
              <div className="relative flex-1 h-3 rounded-full border-2 border-ink overflow-hidden bg-ink/5">
                <div className="absolute top-0 bottom-0 w-px bg-ink/40" style={{ left: "50%" }} />
                <div
                  className={`absolute top-0 bottom-0 ${positive ? "bg-action-stand" : "bg-action-hit"}`}
                  style={evBarStyle(a.ev)}
                />
              </div>
              <span className={`w-10 text-right text-[11px] font-mono ${positive ? "text-action-stand" : "text-action-hit"}`}>
                {evStr(a.ev)}
              </span>
              {best && (
                <span
                  data-testid="bj-best-action"
                  className="px-1.5 py-0.5 rounded-full border-2 border-ink bg-action-stand text-cream text-[9px] uppercase tracking-widest"
                >
                  {t("Best")}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}
