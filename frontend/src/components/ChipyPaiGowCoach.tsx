/**
 * ChipyPaiGowCoach.tsx — Chipy panel for Pai Gow.
 *
 * Mirrors blackjack's ChipyCoach minus blackjack-specific bits. Shows the
 * streaming text + the post-set evaluation banner (was_optimal + ev_loss).
 */
import { useState, useEffect } from "react";
import { usePaiGowStore } from "../store/paiGowStore";
import { getPaiGowOdds } from "../api/client";
import type { PaiGowOdds } from "../types";
import Chipy from "./Chipy";
import PaiGowOddsGraphic from "./PaiGowOddsGraphic";
import { t } from "../i18n";

function stripMarkdown(text: string): string {
  return text
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/__([^_]+?)__/g, "$1")
    .replace(/(?<!\*)\*([^*\n]+?)\*(?!\*)/g, "$1")
    .replace(/`([^`]+?)`/g, "$1")
    .replace(/^\s*[-*+]\s+/gm, "");
}

export default function ChipyPaiGowCoach() {
  const { chipyText, chipyStreaming, chipyPhase, postEvaluation, myHand } = usePaiGowStore();
  const text = stripMarkdown(chipyText);

  // On-demand Fortune-bonus readout — fetched when you ask Chipy.
  const [pgOdds, setPgOdds] = useState<PaiGowOdds | null>(null);
  const [oddsLoading, setOddsLoading] = useState(false);
  const handId = myHand?.id ?? null;
  useEffect(() => setPgOdds(null), [handId]);

  async function askOdds(): Promise<void> {
    if (!handId) return;
    setOddsLoading(true);
    const res = await getPaiGowOdds(handId);
    setOddsLoading(false);
    if (!res.error) setPgOdds(res.data);
  }

  let banner = t("Watchin' the table");
  let expression: "idle" | "thinking" | "happy" = "idle";
  let animation: "idle" | "think" | "bounce" = "idle";

  if (chipyStreaming) {
    banner = chipyPhase === "pre" ? t("Sizin' it up…") : t("Callin' the play…");
    expression = "thinking";
    animation = "think";
  } else if (chipyPhase === "post") {
    banner = t("Last hand");
    expression = "happy";
    animation = "bounce";
  } else if (chipyPhase === "pre") {
    banner = t("Your move");
  }

  return (
    <aside
      className="ink-outline-thick rounded-xl flex flex-col w-full lg:w-72 xl:w-80 self-start"
      style={{ backgroundColor: "#1A0A00", boxShadow: "6px 6px 0 0 #1A0A00" }}
      aria-live="polite"
      aria-busy={chipyStreaming}
    >
      <header
        className="flex items-center gap-3 px-3 py-2 border-b-[3px] border-ink"
        style={{ backgroundColor: "#D4AC0D" }}
      >
        <Chipy size={56} expression={expression} animation={animation} pose="rest" />
        <div className="flex flex-col leading-tight flex-1 min-w-0">
          <h2 className="font-display text-ink text-xl tracking-wider leading-none">
            CHIPY
          </h2>
          <span className="font-flavor text-ink/80 text-xs italic truncate">
            {banner}
          </span>
        </div>
      </header>
      <div
        className="paper-grain p-3 min-h-[120px] flex flex-col items-start gap-2"
        style={{ backgroundColor: "#F5F0E8" }}
      >
        {text !== "" ? (
          <p className="font-body text-ink text-sm leading-relaxed whitespace-pre-line">
            {text}
          </p>
        ) : (
          <p className="font-flavor text-ink/60 text-sm italic">
            {t("Howdy. I'll chime in when there's a play to make.")}
          </p>
        )}
        {!chipyStreaming && postEvaluation !== null && (
          <p
            className={`font-ui text-xs uppercase tracking-widest ${
              postEvaluation.is_optimal ? "text-emerald-700" : "text-amber-700"
            }`}
          >
            {postEvaluation.is_optimal
              ? t("Optimal play.")
              : `${t("Sub-optimal")} — ${t("EV loss")} ${postEvaluation.ev_loss_unit_cents}¢/unit`}
          </p>
        )}
        {handId && (
          <button
            type="button"
            onClick={() => void askOdds()}
            disabled={oddsLoading}
            className="px-2 py-1 text-xs font-ui rounded border-2 border-ink bg-gold-bright text-ink disabled:opacity-40"
            data-testid="paigow-odds-ask"
          >
            {oddsLoading ? t("Reading…") : t("Ask Chipy: Fortune odds")}
          </button>
        )}
        {pgOdds && <PaiGowOddsGraphic odds={pgOdds} />}
      </div>
    </aside>
  );
}
