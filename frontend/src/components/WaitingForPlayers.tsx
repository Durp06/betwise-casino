/**
 * WaitingForPlayers — a calm, living panel shown when you're seated at a Hold'em
 * table that doesn't yet have enough players to deal. Hold'em is human-vs-human:
 * with only one seat taken there's no hand to deal and nothing to animate, so the
 * felt would otherwise sit dead. This replaces that void with a clear "waiting for
 * someone to sit down" state + a gentle pulse. Pure presentational — the page
 * decides when to show it.
 */
import { motion } from "framer-motion";
import { t } from "../i18n";

interface WaitingForPlayersProps {
  seated: number;
  needed: number;
}

export default function WaitingForPlayers({ seated, needed }: WaitingForPlayersProps) {
  return (
    <div
      data-testid="holdem-waiting-for-players"
      role="status"
      aria-live="polite"
      className="flex flex-col items-center gap-3 px-6 py-4 rounded-xl border-[3px] border-dashed border-ink/40 bg-ink/30 text-cream"
    >
      <div className="flex items-center gap-2" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="w-2.5 h-2.5 rounded-full bg-gold-bright"
            animate={{ opacity: [0.3, 1, 0.3], scale: [0.85, 1.1, 0.85] }}
            transition={{ repeat: Infinity, duration: 1.2, delay: i * 0.18, ease: "easeInOut" }}
          />
        ))}
      </div>
      <p className="font-flavor italic text-sm text-cream/80">
        {t("Waiting for another player to sit down…")}
      </p>
      <p className="font-ui text-xs uppercase tracking-widest text-cream/60">
        {seated}/{needed} {t("players")}
      </p>
    </div>
  );
}
