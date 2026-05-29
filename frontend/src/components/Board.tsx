/**
 * Board.tsx — community cards row (flop 3 / turn 4 / river 5).
 *
 * Renders 0, 3, 4, or 5 cards. Empty placeholders indicate where cards will
 * appear. Reuses PlayingCard so visual consistency with hole cards.
 */
import type { PokerCard } from "../types";
import PlayingCard from "./PlayingCard";

interface BoardProps {
  cards: PokerCard[];
}

export default function Board({ cards }: BoardProps) {
  // Render up to 5 slots, filled with cards then empty placeholders.
  const slots: (PokerCard | null)[] = [];
  for (let i = 0; i < 5; i++) {
    slots.push(i < cards.length ? cards[i] : null);
  }

  return (
    <div className="flex gap-2 justify-center items-center" data-testid="board">
      {slots.map((c, idx) =>
        c === null ? (
          <div
            key={idx}
            className="w-12 h-16 rounded border-2 border-dashed border-ink/30"
            data-testid="board-empty-slot"
          />
        ) : (
          <PlayingCard key={idx} card={c} index={idx} noAnimate />
        ),
      )}
    </div>
  );
}
