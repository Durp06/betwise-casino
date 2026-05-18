/**
 * CardHand.tsx — horizontal hand layout with brass-coin value badge.
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
    <div className="flex flex-col items-center gap-3">
      {label && (
        <span className="font-display text-cream text-base uppercase tracking-widest">
          {t(label)}
        </span>
      )}

      <div className="flex flex-row justify-center gap-2 deal-stagger">
        {cards.length === 0 ? (
          <span className="font-flavor text-cream/60 italic text-sm">{t("No cards")}</span>
        ) : (
          cards.map((card, idx) => (
            <PlayingCard key={idx} card={card} index={idx} />
          ))
        )}
      </div>

      {handValue !== undefined && handValue !== null && (
        <span
          className="ink-outline-thick font-display text-3xl px-5 py-1 rounded-full"
          style={{
            backgroundColor: "#F4D03F",
            color: "#1A0A00",
            boxShadow: "4px 4px 0 0 #1A0A00",
          }}
          aria-label={`Hand value ${handValue}`}
        >
          {handValue}
        </span>
      )}
    </div>
  );
}
