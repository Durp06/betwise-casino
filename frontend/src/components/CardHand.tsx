/**
 * CardHand.tsx — lays out a player's or dealer's cards horizontally.
 * Accepts (Card | null)[] for face-down/placeholder support.
 */
import type { Card } from "../types";
import PlayingCard from "./PlayingCard";
import { t } from "../i18n";

interface CardHandProps {
  cards: (Card | null)[];
  handValue?: number | null;
  label?: string;
}

export default function CardHand({ cards, handValue, label }: CardHandProps) {
  return (
    <div className="flex flex-col items-start gap-1">
      {label && (
        <span className="text-xs text-white/60 font-medium uppercase tracking-wide">
          {t(label)}
        </span>
      )}
      <div className="flex flex-row flex-wrap gap-1">
        {cards.length === 0 ? (
          <span className="text-white/40 text-sm italic">{t("No cards")}</span>
        ) : (
          cards.map((card, idx) => (
            <PlayingCard key={idx} card={card} />
          ))
        )}
      </div>
      {handValue !== undefined && handValue !== null && (
        <span className="text-xs font-bold text-chip-gold bg-chipy-dark px-2 py-0.5 rounded-full">
          {handValue}
        </span>
      )}
    </div>
  );
}
