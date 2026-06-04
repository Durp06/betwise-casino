/**
 * HoldemSeat.tsx — one chair at a multiplayer Hold'em table.
 *
 * Every occupant is a human, so we show their username. Hole cards deal from
 * the deck, masked for opponents until showdown. SeatMotion dims folded players
 * and pulses the seat on the clock; ActionBadge shows what they just did.
 */
import { motion } from "framer-motion";
import type { HoldemHandSeatState, HoldemSeat as HoldemSeatType, Card } from "../types";
import AnimatedCardRow from "./AnimatedCardRow";
import SeatMotion from "./SeatMotion";
import ActionBadge from "./ActionBadge";
import AnimatedCounter from "./AnimatedCounter";
import { useDeckContext } from "../motion/DeckProvider";
import { t } from "../i18n";

interface HoldemSeatProps {
  chairNumber: number;
  occupant: HoldemSeatType | null;
  handSeat: HoldemHandSeatState | null;
  isCurrentToAct: boolean;
  isButton: boolean;
  isYou: boolean;
  lastAction?: string | null;
  lastActionAmount?: number;
}

export default function HoldemSeat({
  chairNumber,
  occupant,
  handSeat,
  isCurrentToAct,
  isButton,
  isYou,
  lastAction = null,
  lastActionAmount = 0,
}: HoldemSeatProps) {
  const ctx = useDeckContext();
  const empty = occupant === null && handSeat === null;
  const username = handSeat?.username ?? occupant?.username ?? null;
  const stack = handSeat?.final_stack ?? occupant?.stack ?? 0;
  const hole = handSeat?.hole_cards ?? [];
  const currentBet = handSeat?.current_bet ?? 0;
  const isFolded = handSeat?.is_folded ?? false;
  const isAllIn = handSeat?.is_all_in ?? false;
  const engineSeat = handSeat?.seat_number;

  const borderClass = isCurrentToAct
    ? "border-action-hit ring-4 ring-action-hit/30"
    : "border-ink";

  if (empty) {
    // Open chairs gently breathe (staggered) so an unfilled felt feels alive and
    // inviting rather than dead. Opacity-only so it survives reduced-motion.
    return (
      <motion.div
        className="flex flex-col items-center justify-center gap-1 p-2 rounded-xl border-[3px] border-dashed border-ink/30 bg-cream/40 min-h-[96px]"
        data-testid={`holdem-seat-${chairNumber}`}
        animate={{ opacity: [0.55, 0.9, 0.55] }}
        transition={{ repeat: Infinity, duration: 2.6, delay: (chairNumber % 6) * 0.18, ease: "easeInOut" }}
      >
        <span className="text-ink/40 text-xs italic">{t("Empty seat")}</span>
      </motion.div>
    );
  }

  return (
    <SeatMotion isFolded={isFolded} isCurrentToAct={isCurrentToAct}>
      <ActionBadge action={lastAction} amount={lastActionAmount} />
      <div
        ref={(el) => {
          if (engineSeat !== undefined) ctx?.registerSeat(engineSeat, el);
        }}
        className={`flex flex-col items-center gap-1 p-2 rounded-xl border-[3px] ${borderClass} bg-cream`}
        data-testid={`holdem-seat-${chairNumber}`}
      >
        {/* Hole cards — dealt from the deck (compact) */}
        {hole.length === 0 ? (
          <span className="text-ink/30 text-xs italic">{t("—")}</span>
        ) : (
          <AnimatedCardRow cards={hole as (Card | null)[]} size="sm" className="gap-1" />
        )}

        {/* Name + dealer button */}
        <div className="flex items-center gap-1">
          <span
            className="text-xs font-ui text-ink max-w-[7rem] truncate"
            data-testid={`holdem-seat-name-${chairNumber}`}
          >
            {username ?? t("Player")}
          </span>
          {isButton && (
            <span
              className="text-[10px] font-ui px-1 rounded-full bg-gold-bright text-ink border border-ink"
              data-testid="dealer-button-indicator"
            >
              D
            </span>
          )}
        </div>

        {/* Stack */}
        <div className="text-xs font-mono text-ink" data-testid={`holdem-seat-stack-${chairNumber}`}>
          <AnimatedCounter value={stack} />
        </div>

        {/* Current bet */}
        {currentBet > 0 && (
          <div
            className="text-xs font-mono text-gold-bright bg-ink px-1 rounded"
            data-testid={`holdem-seat-bet-${chairNumber}`}
          >
            {currentBet}
          </div>
        )}

        {/* State labels */}
        {isFolded && (
          <span className="text-[10px] uppercase font-ui text-ink/60">{t("Folded")}</span>
        )}
        {isAllIn && !isFolded && (
          <span className="text-[10px] uppercase font-ui text-action-hit">{t("All-in")}</span>
        )}
        {isYou && (
          <span className="text-[10px] uppercase font-ui text-action-stand" data-testid="you-marker">
            {t("you")}
          </span>
        )}
      </div>
    </SeatMotion>
  );
}
