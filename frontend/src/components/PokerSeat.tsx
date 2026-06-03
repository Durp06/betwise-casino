/**
 * PokerSeat.tsx — renders one seat at the poker table.
 *
 * Shows: archetype badge, stack, current bet, dealer button, fold/all-in state,
 * a pulsing ring when it's their turn (SeatMotion), and a transient ActionBadge
 * of what they just did. Hole cards deal from the deck (masked for opponents).
 */
import type { Card, PokerHandSeatState, PokerSeat as PokerSeatType } from "../types";
import AnimatedCardRow from "./AnimatedCardRow";
import ArchetypeBadge from "./ArchetypeBadge";
import SeatMotion from "./SeatMotion";
import ActionBadge from "./ActionBadge";
import AnimatedCounter from "./AnimatedCounter";
import { useDeckContext } from "../motion/DeckProvider";
import { t } from "../i18n";

interface PokerSeatProps {
  seat: PokerSeatType;
  handSeat: PokerHandSeatState | null;
  isCurrentToAct: boolean;
  isButton: boolean;
  isYou: boolean;
  lastAction?: string | null;
  lastActionAmount?: number;
}

export default function PokerSeat({
  seat,
  handSeat,
  isCurrentToAct,
  isButton,
  isYou,
  lastAction = null,
  lastActionAmount = 0,
}: PokerSeatProps) {
  const ctx = useDeckContext();
  const hole = handSeat?.hole_cards ?? [];
  const stack = handSeat?.final_stack ?? seat.current_stack;
  const currentBet = handSeat?.current_bet ?? 0;
  const isFolded = handSeat?.is_folded ?? false;
  const isAllIn = handSeat?.is_all_in ?? false;
  const isBust = seat.is_bust;

  const borderClass = isCurrentToAct
    ? "border-action-hit ring-4 ring-action-hit/30"
    : "border-ink";

  return (
    <SeatMotion isFolded={isFolded || isBust} isCurrentToAct={isCurrentToAct}>
      <ActionBadge action={lastAction} amount={lastActionAmount} />
      <div
        ref={(el) => ctx?.registerSeat(seat.seat_number, el)}
        className={`flex flex-col items-center gap-1 p-2 rounded-xl border-[3px] ${borderClass} bg-cream`}
        data-testid={`poker-seat-${seat.seat_number}`}
      >
        {/* Hole cards — dealt from the deck (compact) */}
        {hole.length === 0 ? (
          <span className="text-ink/30 text-xs italic">{t("(no cards)")}</span>
        ) : (
          <AnimatedCardRow cards={hole as (Card | null)[]} size="sm" className="gap-1" />
        )}

        {/* Name + archetype */}
        <div className="flex items-center gap-1">
          <ArchetypeBadge archetypeName={seat.archetype_name} isBot={seat.is_bot} />
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
        <div className="text-xs font-mono text-ink" data-testid={`seat-stack-${seat.seat_number}`}>
          <AnimatedCounter value={stack} />
        </div>

        {/* Current bet (if any) */}
        {currentBet > 0 && (
          <div
            className="text-xs font-mono text-gold-bright bg-ink px-1 rounded"
            data-testid={`seat-bet-${seat.seat_number}`}
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
        {isBust && !isFolded && (
          <span className="text-[10px] uppercase font-ui text-red-700">{t("Bust")}</span>
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
