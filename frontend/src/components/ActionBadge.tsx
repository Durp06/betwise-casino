/**
 * ActionBadge — the transient "what this seat just did" chip that pops above a
 * seat (RAISE / BET / CALL / CHECK / FOLD / ALL-IN / YOUR TURN) and auto-dismisses.
 * Presentational: the parent sets `action` (and clears it on a timer).
 */
import { AnimatePresence, motion } from "framer-motion";
import { BADGE_POP } from "../motion/tokens";
import { formatMoney } from "../utils/money";
import { t } from "../i18n";

const STYLE: Record<string, string> = {
  fold: "bg-ink text-cream",
  check: "bg-action-stand text-cream",
  call: "bg-action-double text-cream",
  bet: "bg-gold-bright text-ink",
  raise: "bg-gold-bright text-ink",
  all_in: "bg-action-hit text-cream",
  turn: "bg-action-double text-cream",
};

function label(action: string, amount: number): string {
  switch (action) {
    case "fold": return t("Fold");
    case "check": return t("Check");
    case "call": return amount > 0 ? `${t("Call")} ${formatMoney(amount)}` : t("Call");
    case "bet": return amount > 0 ? `${t("Bet")} ${formatMoney(amount)}` : t("Bet");
    case "raise": return amount > 0 ? `${t("Raise")} ${formatMoney(amount)}` : t("Raise");
    case "all_in": return t("All-in");
    case "turn": return t("To act");
    default: return action.toUpperCase();
  }
}

interface ActionBadgeProps {
  action: string | null;
  amount?: number;
}

export default function ActionBadge({ action, amount = 0 }: ActionBadgeProps) {
  return (
    <AnimatePresence>
      {action && (
        <motion.div
          key={action}
          initial={{ scale: 0.6, opacity: 0, y: -4 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.6, opacity: 0, y: -10 }}
          transition={BADGE_POP}
          className={`absolute -top-3 left-1/2 -translate-x-1/2 z-30 px-2 py-0.5 rounded-full
            border-2 border-ink font-ui text-[10px] uppercase tracking-widest whitespace-nowrap
            shadow-[2px_2px_0_0_#1A0A00] ${STYLE[action] ?? "bg-cream text-ink"}`}
        >
          {label(action, amount)}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
