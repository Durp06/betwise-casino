/**
 * PokerOddsGraphic — Chipy's visual hand-odds readout for Texas Hold'em
 * (shared by the solo trainer and multiplayer Hold'em).
 *
 * Shows the Monte-Carlo win/tie/lose equity as a big number + stacked bar, the
 * current made hand, and a pot-odds verdict (+EV call / -EV fold) when there's
 * a bet to call. Purely presentational — fed a PokerOdds payload.
 */
import { motion } from "framer-motion";
import type { PokerOdds } from "../types";
import { t } from "../i18n";

function pct(x: number): string {
  return `${Math.round(Math.max(0, Math.min(1, x)) * 100)}%`;
}

export default function PokerOddsGraphic({ odds }: { odds: PokerOdds | null }) {
  if (!odds) return null;
  const win = Math.max(0, odds.win_pct);
  const tie = Math.max(0, odds.tie_pct);
  const lose = Math.max(0, odds.lose_pct);
  const hasCall = odds.pot_odds_pct > 0;
  const need = odds.pot_odds_pct;
  // Equity for the call decision: a tie chops the pot, so it isn't a loss.
  const equityForCall = win + tie;
  const profitable = equityForCall >= need;

  return (
    <motion.div
      data-testid="poker-odds-graphic"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="ink-outline rounded-lg p-3 flex flex-col gap-2 bg-cream text-ink"
    >
      <div className="flex items-baseline justify-between">
        <span className="font-ui uppercase tracking-widest text-[10px] text-ink/70">
          {t("Hand odds")}
        </span>
        <span className="font-ui text-[10px] text-ink/60">
          {t("vs")} {odds.n_opponents}{" "}
          {odds.n_opponents === 1 ? t("opponent") : t("opponents")}
        </span>
      </div>

      {/* Win equity — headline + stacked bar */}
      <div className="flex items-end gap-2">
        <span className="font-display text-3xl leading-none text-action-stand" data-testid="odds-win-pct">
          {pct(win)}
        </span>
        <span className="font-flavor italic text-xs text-ink/60 mb-1">{t("to win")}</span>
      </div>
      <div className="flex h-4 w-full overflow-hidden rounded-full border-2 border-ink" aria-hidden="true">
        <div className="bg-action-stand h-full" style={{ width: pct(win) }} />
        <div className="bg-gold-bright h-full" style={{ width: pct(tie) }} />
        <div className="bg-action-hit h-full" style={{ width: pct(lose) }} />
      </div>
      <div className="flex justify-between text-[10px] font-ui uppercase tracking-wider text-ink/60">
        <span>{t("Win")} {pct(win)}</span>
        {tie > 0.005 && <span>{t("Tie")} {pct(tie)}</span>}
        <span>{t("Lose")} {pct(lose)}</span>
      </div>

      {/* Current made hand */}
      {odds.made_hand && (
        <div className="text-xs font-ui">
          <span className="text-ink/60 uppercase tracking-wider text-[10px]">{t("You have")}: </span>
          <span className="font-display text-base capitalize">{odds.made_hand}</span>
        </div>
      )}

      {/* Pot-odds verdict */}
      {hasCall ? (
        <div className="flex items-center justify-between gap-2 border-t-2 border-ink/15 pt-2">
          <span className="text-[11px] font-flavor text-ink/80">
            {t("Pot odds: need")} <b>{pct(need)}</b> · {t("you have")} <b>{pct(equityForCall)}</b>
          </span>
          <span
            data-testid="odds-verdict"
            className={`shrink-0 px-2 py-0.5 rounded-full border-2 border-ink font-ui text-[10px] uppercase tracking-widest ${
              profitable ? "bg-action-stand text-cream" : "bg-action-hit text-cream"
            }`}
          >
            {profitable ? t("+EV Call") : t("-EV Fold")}
          </span>
        </div>
      ) : (
        <div className="border-t-2 border-ink/15 pt-2 text-[11px] font-flavor italic text-ink/60">
          {t("Nothing to call — free to see the next card.")}
        </div>
      )}
    </motion.div>
  );
}
