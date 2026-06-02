/**
 * PaiGowCard.tsx — render a PaiGowCard (delegates to PlayingCard for the
 * 52 standard cards; renders a "JOKER" face for the sentinel).
 */
import type { Card } from "../types";
import type { PaiGowCard as PaiGowCardType } from "../types";
import PlayingCard from "./PlayingCard";
import { t } from "../i18n";

interface Props {
  card: PaiGowCardType | null;
  className?: string;
  index?: number;
  noAnimate?: boolean;
}

export default function PaiGowCard({ card, className = "", index = 0, noAnimate = false }: Props) {
  if (card === null) {
    return <PlayingCard card={null} className={className} index={index} noAnimate={noAnimate} />;
  }
  if (card.suit === "joker") {
    return (
      <div
        className={`paper-grain ink-outline-thick w-16 h-24 sm:w-20 sm:h-28 rounded-md
          relative flex items-center justify-center ${className}`}
        aria-label={t("Joker card")}
        style={{ backgroundColor: "#F5F0E8", boxShadow: "4px 4px 0 0 #1A0A00" }}
      >
        <span className="font-display text-ink text-xs tracking-widest rotate-[-15deg]">
          JOKER
        </span>
      </div>
    );
  }
  // Safe cast — we just checked it's not the joker sentinel.
  return (
    <PlayingCard
      card={card as Card}
      className={className}
      index={index}
      noAnimate={noAnimate}
    />
  );
}
