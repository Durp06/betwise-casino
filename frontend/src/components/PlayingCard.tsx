/**
 * PlayingCard.tsx — renders a single playing card (face-up or face-down).
 * null → face-down back of card.
 */
import type { Card } from "../types";
import { t } from "../i18n";

interface PlayingCardProps {
  card: Card | null;
  className?: string;
}

const SUIT_SYMBOLS: Record<string, string> = {
  hearts: "♥",
  diamonds: "♦",
  clubs: "♣",
  spades: "♠",
};

const RED_SUITS = new Set(["hearts", "diamonds"]);

export default function PlayingCard({ card, className = "" }: PlayingCardProps) {
  if (!card) {
    // Face-down card
    return (
      <div
        className={`w-12 h-20 sm:w-14 sm:h-24 rounded-lg border-2 border-white/30
          bg-felt-green flex items-center justify-center shadow-md ${className}`}
        aria-label={t("Face-down card")}
      >
        <div className="w-8 h-14 sm:w-10 sm:h-18 rounded border border-white/20
          bg-gradient-to-br from-felt-green to-green-900" />
      </div>
    );
  }

  const isRed = RED_SUITS.has(card.suit);
  const symbol = SUIT_SYMBOLS[card.suit] ?? card.suit;

  return (
    <div
      className={`w-12 h-20 sm:w-14 sm:h-24 rounded-lg border-2 border-gray-300
        bg-white flex flex-col justify-between p-1 shadow-md ${className}`}
      aria-label={`${card.value} of ${card.suit}`}
    >
      <span className={`text-sm font-bold leading-none ${isRed ? "text-card-red" : "text-gray-900"}`}>
        {card.value}
      </span>
      <span className={`text-xl self-center ${isRed ? "text-card-red" : "text-gray-900"}`}>
        {symbol}
      </span>
      <span className={`text-sm font-bold leading-none self-end rotate-180 ${isRed ? "text-card-red" : "text-gray-900"}`}>
        {card.value}
      </span>
    </div>
  );
}
