/**
 * PokerSeat.tsx — renders one seat at the poker table.
 *
 * Shows: archetype badge, stack, current bet, dealer button (if applicable),
 * fold/all-in state, action highlight when it's their turn. Hole cards are
 * rendered above the seat — masked (null entries) for opponents during play.
 */
import type { PokerCard, PokerHandSeatState, PokerSeat as PokerSeatType } from "../types";
import PlayingCard from "./PlayingCard";
import ArchetypeBadge from "./ArchetypeBadge";
import { t } from "../i18n";

interface PokerSeatProps {
  seat: PokerSeatType;
  handSeat: PokerHandSeatState | null;
  isCurrentToAct: boolean;
  isButton: boolean;
  isYou: boolean;
}

export default function PokerSeat({
  seat,
  handSeat,
  isCurrentToAct,
  isButton,
  isYou,
}: PokerSeatProps) {
  const hole = handSeat?.hole_cards ?? [];
  const stack = handSeat?.final_stack ?? seat.current_stack;
  const currentBet = handSeat?.current_bet ?? 0;
  const isFolded = handSeat?.is_folded ?? false;
  const isAllIn = handSeat?.is_all_in ?? false;
  const isBust = seat.is_bust;

  const borderClass = isCurrentToAct
    ? "border-action-hit ring-4 ring-action-hit/30"
    : "border-ink";

  const opacity = isFolded || isBust ? "opacity-40" : "opacity-100";

  return (
    <div
      className={`flex flex-col items-center gap-1 p-2 rounded-xl border-[3px] ${borderClass} bg-cream ${opacity}`}
      data-testid={`poker-seat-${seat.seat_number}`}
    >
      {/* Hole cards */}
      <div className="flex gap-1">
        {hole.length === 0 ? (
          <span className="text-ink/30 text-xs italic">{t("(no cards)")}</span>
        ) : (
          hole.map((card: PokerCard | null, idx: number) =>
            card === null ? (
              <div
                key={idx}
                className="w-8 h-12 rounded border-2 border-ink bg-blue-900"
                data-testid="hole-card-back"
              />
            ) : (
              <PlayingCard key={idx} card={card} index={idx} noAnimate />
            ),
          )
        )}
      </div>

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
        {stack}
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
  );
}
