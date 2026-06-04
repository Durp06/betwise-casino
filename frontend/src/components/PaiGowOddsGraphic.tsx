/**
 * PaiGowOddsGraphic — Chipy's Fortune-bonus readout. Shows the Fortune pay
 * ladder and highlights which tier the player's dealt 7 cards qualify for.
 */
import { motion } from "framer-motion";
import type { PaiGowOdds } from "../types";
import { t } from "../i18n";

export default function PaiGowOddsGraphic({ odds }: { odds: PaiGowOdds | null }) {
  if (!odds) return null;
  const ladder: { key: string; label: string; pay: string }[] = [
    { key: "seven_card_sf", label: t("7-Card Straight Flush"), pay: t("GRAND") },
    { key: "royal_flush", label: t("Royal Flush"), pay: t("MAJOR") },
    { key: "straight_flush", label: t("Straight Flush"), pay: "200×" },
    { key: "four_of_a_kind", label: t("Four of a Kind"), pay: "50×" },
    { key: "full_house", label: t("Full House"), pay: "5×" },
    { key: "flush", label: t("Flush"), pay: "4×" },
    { key: "straight", label: t("Straight"), pay: "3×" },
    { key: "three_of_a_kind", label: t("Three of a Kind"), pay: "2×" },
  ];
  const hit = odds.fortune_category;
  const hitRow = ladder.find((r) => r.key === hit);

  return (
    <motion.div
      data-testid="paigow-odds-graphic"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="ink-outline rounded-lg p-3 flex flex-col gap-2 bg-cream text-ink"
    >
      <div className="flex items-baseline justify-between">
        <span className="font-ui uppercase tracking-widest text-[10px] text-ink/70">{t("Fortune bonus")}</span>
        {!odds.placed_fortune_bet && (
          <span className="font-flavor italic text-[10px] text-ink/50">{t("no Fortune bet this hand")}</span>
        )}
      </div>

      <div className="flex flex-col gap-0.5">
        {ladder.map((r) => {
          const on = r.key === hit;
          return (
            <div
              key={r.key}
              className={`flex justify-between items-center px-2 py-0.5 rounded ${
                on ? "bg-gold-bright border-2 border-ink font-bold" : "text-ink/70"
              }`}
              data-testid={on ? "paigow-fortune-hit" : undefined}
            >
              <span className="text-xs">{r.label}</span>
              <span className="text-xs font-ui">{r.pay}</span>
            </div>
          );
        })}
      </div>

      <p className="font-flavor italic text-[11px] text-ink/70 border-t-2 border-ink/15 pt-2">
        {hitRow
          ? `${t("Your hand qualifies for")} ${hitRow.label}!`
          : t("No Fortune hand — needs three of a kind or better.")}
      </p>
    </motion.div>
  );
}
