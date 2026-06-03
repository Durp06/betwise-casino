/**
 * AnimatedCardRow — a horizontal row of DealtCards with stable identity keys.
 *
 * Fixes the "keyed by index → can't re-animate" bug: keys each card by its
 * content + slot so appending a card (turn/river, a hit) mounts exactly one new
 * DealtCard (which deals from the deck) while existing cards keep their place,
 * and folds unmount with the muck exit. Wrap usage in a stable parent keyed by
 * hand id so a fresh hand re-deals.
 */
import { AnimatePresence } from "framer-motion";
import DealtCard from "./DealtCard";
import type { Card } from "../types";

interface AnimatedCardRowProps {
  cards: (Card | null)[];
  /** Resolve face-up per slot. Default: face up when a card is present. */
  faceUp?: (card: Card | null, index: number) => boolean;
  dealFromDeck?: boolean;
  className?: string;
}

export default function AnimatedCardRow({
  cards,
  faceUp,
  dealFromDeck = true,
  className = "",
}: AnimatedCardRowProps) {
  return (
    <div className={`flex flex-row justify-center gap-2 ${className}`}>
      <AnimatePresence initial={false}>
        {cards.map((card, i) => {
          const key = card ? `${card.suit}-${card.value}-${i}` : `back-${i}`;
          const isUp = faceUp ? faceUp(card, i) : card !== null;
          return (
            <DealtCard
              key={key}
              card={card}
              index={i}
              faceUp={isUp}
              dealFromDeck={dealFromDeck}
            />
          );
        })}
      </AnimatePresence>
    </div>
  );
}
