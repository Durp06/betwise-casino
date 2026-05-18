/**
 * PlayingCard.tsx — renders a single playing card (face-up or face-down).
 * null → face-down back of card.
 *
 * 3D + motion: layered shadows (close/mid/far) for depth, slight rotation
 * jitter so a row of cards reads as "dealt" not "lined up." Deal-in
 * animation fires on mount; staggered via parent's .deal-stagger.
 */
import type { Card } from "../types";
import { t } from "../i18n";

interface PlayingCardProps {
  card: Card | null;
  className?: string;
  /** Index in the hand — used for slight rotation jitter */
  index?: number;
  /** Skip the deal-in animation (e.g. for already-shown cards on poll) */
  noAnimate?: boolean;
}

const SUIT_SYMBOLS: Record<string, string> = {
  hearts:   "♥",
  diamonds: "♦",
  clubs:    "♣",
  spades:   "♠",
};

const RED_SUITS = new Set(["hearts", "diamonds"]);

// Light, deterministic rotation jitter based on index — so cards in a row
// look like they were tossed, not stacked. Kept very subtle (±1.6°) so
// the cards read as upright but not aligned to a CAD grid.
function jitterRotation(index: number): string {
  const pattern = [-1.6, 0.8, -0.5, 1.2, -1.0, 1.5];
  return `${pattern[index % pattern.length]}deg`;
}

const CARD_BOX_SHADOW =
  // close, sharp shadow for definition
  "0 1px 2px rgba(0, 0, 0, 0.45), " +
  // mid, soft shadow for surface lift
  "0 6px 10px -4px rgba(0, 0, 0, 0.55), " +
  // far, broad shadow for room depth
  "0 18px 24px -12px rgba(0, 0, 0, 0.5), " +
  // brass-tone ring edge
  "0 0 0 1px rgba(58, 38, 28, 0.5), " +
  // inset top highlight from the candle
  "inset 0 1px 0 rgba(255, 240, 200, 0.55)";

export default function PlayingCard({
  card,
  className = "",
  index = 0,
  noAnimate = false,
}: PlayingCardProps) {
  const rotation = jitterRotation(index);
  const animClass = noAnimate ? "" : "card-deal-in";

  if (!card) {
    // Face-down — walnut back with a brass-tinted lattice
    return (
      <div
        className={`${animClass} w-14 h-20 sm:w-16 sm:h-24 rounded-md
          flex items-center justify-center ${className}`}
        aria-label={t("Face-down card")}
        style={{
          backgroundColor: "#241812",
          backgroundImage:
            "linear-gradient(135deg, rgba(138,106,55,0.30) 25%, transparent 25%, transparent 50%, rgba(138,106,55,0.30) 50%, rgba(138,106,55,0.30) 75%, transparent 75%, transparent)",
          backgroundSize: "10px 10px",
          boxShadow:
            "inset 0 0 0 2px #3a261c, inset 0 0 0 3px rgba(138,106,55,0.55), 0 1px 2px rgba(0,0,0,0.45), 0 6px 10px -4px rgba(0,0,0,0.55), 0 18px 24px -12px rgba(0,0,0,0.5)",
          transform: `rotate(${rotation})`,
        }}
      />
    );
  }

  const isRed = RED_SUITS.has(card.suit);
  const symbol = SUIT_SYMBOLS[card.suit] ?? card.suit;
  const pipColor = isRed ? "#7e2424" : "#1d1208";

  return (
    <div
      className={`saloon-card ${animClass} relative
        w-14 h-20 sm:w-16 sm:h-24 rounded-md
        flex flex-col justify-between p-1.5 ${className}`}
      aria-label={`${card.value} of ${card.suit}`}
      style={{
        boxShadow: CARD_BOX_SHADOW,
        transform: `rotate(${rotation})`,
      }}
    >
      <span
        className="text-sm font-bold leading-none"
        style={{
          color: pipColor,
          fontFamily: "'DM Serif Display', Georgia, serif",
          textShadow: "0 1px 0 rgba(255, 255, 255, 0.6)",
        }}
      >
        {card.value}
      </span>
      <span
        className="text-2xl self-center leading-none"
        style={{
          color: pipColor,
          textShadow: "0 1px 0 rgba(255, 255, 255, 0.5)",
        }}
      >
        {symbol}
      </span>
      <span
        className="text-sm font-bold leading-none self-end rotate-180"
        style={{
          color: pipColor,
          fontFamily: "'DM Serif Display', Georgia, serif",
          textShadow: "0 1px 0 rgba(255, 255, 255, 0.6)",
        }}
      >
        {card.value}
      </span>
    </div>
  );
}
