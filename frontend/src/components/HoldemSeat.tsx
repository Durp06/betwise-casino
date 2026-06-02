/**
 * HoldemSeat.tsx — one chair at a multiplayer Hold'em table.
 *
 * Unlike the solo trainer's PokerSeat (which shows a bot archetype), every
 * occupant here is a human, so we show their username. Hole cards are masked
 * (null entries → card backs) for opponents until showdown. Highlights the
 * chair whose turn it is; dims folded players.
 */
import type { HoldemHandSeatState, HoldemSeat as HoldemSeatType, PokerCard } from "../types";
import PlayingCard from "./PlayingCard";
import { t } from "../i18n";

interface HoldemSeatProps {
  chairNumber: number;
  occupant: HoldemSeatType | null;
  handSeat: HoldemHandSeatState | null;
  isCurrentToAct: boolean;
  isButton: boolean;
  isYou: boolean;
}

export default function HoldemSeat({
  chairNumber,
  occupant,
  handSeat,
  isCurrentToAct,
  isButton,
  isYou,
}: HoldemSeatProps) {
  const empty = occupant === null && handSeat === null;
  const username = handSeat?.username ?? occupant?.username ?? null;
  const stack = handSeat?.final_stack ?? occupant?.stack ?? 0;
  const hole = handSeat?.hole_cards ?? [];
  const currentBet = handSeat?.current_bet ?? 0;
  const isFolded = handSeat?.is_folded ?? false;
  const isAllIn = handSeat?.is_all_in ?? false;

  const borderClass = isCurrentToAct
    ? "border-action-hit ring-4 ring-action-hit/30"
    : "border-ink";
  const opacity = isFolded ? "opacity-40" : "opacity-100";

  if (empty) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-1 p-2 rounded-xl border-[3px] border-dashed border-ink/30 bg-cream/40 min-h-[96px]"
        data-testid={`holdem-seat-${chairNumber}`}
      >
        <span className="text-ink/40 text-xs italic">{t("Empty seat")}</span>
      </div>
    );
  }

  return (
    <div
      className={`flex flex-col items-center gap-1 p-2 rounded-xl border-[3px] ${borderClass} bg-cream ${opacity}`}
      data-testid={`holdem-seat-${chairNumber}`}
    >
      {/* Hole cards */}
      <div className="flex gap-1">
        {hole.length === 0 ? (
          <span className="text-ink/30 text-xs italic">{t("—")}</span>
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
        {stack}
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
  );
}
