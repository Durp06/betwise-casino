/**
 * Board.tsx — community cards row (flop 3 / turn 4 / river 5).
 *
 * Empty slots are dashed placeholders; as each street is dealt the new card
 * flies in from the deck (DealtCard). Placeholders match card size so the row
 * doesn't jump when a card lands.
 */
import type { PokerCard, Card } from "../types";
import DealtCard from "./DealtCard";

interface BoardProps {
  cards: PokerCard[];
}

export default function Board({ cards }: BoardProps) {
  const slots: (PokerCard | null)[] = [];
  for (let i = 0; i < 5; i++) {
    slots.push(i < cards.length ? cards[i] : null);
  }

  return (
    <div className="flex gap-2 justify-center items-center" data-testid="board">
      {slots.map((c, idx) =>
        c === null ? (
          <div
            key={`empty-${idx}`}
            className="w-16 h-24 sm:w-20 sm:h-28 rounded-md border-2 border-dashed border-cream/25"
            data-testid="board-empty-slot"
          />
        ) : (
          <DealtCard key={`${c.suit}-${c.value}-${idx}`} card={c as Card} index={idx} faceUp />
        ),
      )}
    </div>
  );
}
