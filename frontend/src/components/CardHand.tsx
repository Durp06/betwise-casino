/**
 * CardHand.tsx — lays out a player's or dealer's cards horizontally.
 * Accepts (Card | null)[] for face-down/placeholder support.
 *
 * Layout: cards overlap slightly (negative margin) so a row reads as a
 * "fanned hand" rather than a tile grid. Deal animation cascades via
 * the parent .deal-stagger class (see index.css).
 */
import type { Card } from "../types";
import PlayingCard from "./PlayingCard";
import { t } from "../i18n";

interface CardHandProps {
  cards: (Card | null)[];
  handValue?: number | null;
  /** Optional small label rendered above the cards. Most callers render
   *  their own label in saloon style — leave this blank in those cases. */
  label?: string;
}

export default function CardHand({ cards, handValue, label }: CardHandProps) {
  return (
    <div className="flex flex-col items-center gap-2">
      {label && (
        <span className="text-[10px] uppercase tracking-[0.3em] text-saloon-amber/70">
          {t(label)}
        </span>
      )}

      <div className="flex flex-row justify-center gap-1.5 sm:gap-2 deal-stagger">
        {cards.length === 0 ? (
          <span className="text-saloon-ash italic text-sm">{t("No cards")}</span>
        ) : (
          cards.map((card, idx) => (
            <PlayingCard key={idx} card={card} index={idx} />
          ))
        )}
      </div>

      {handValue !== undefined && handValue !== null && (
        <span
          className="text-sm font-bold tracking-wide"
          style={{
            fontFamily: "'DM Serif Display', Georgia, serif",
            color: "#1d1208",
            background:
              "radial-gradient(60% 60% at 50% 35%, #e7a55b 0%, #b3742a 100%)",
            padding: "2px 12px",
            borderRadius: "9999px",
            boxShadow:
              "inset 0 1px 0 rgba(255, 240, 200, 0.55), " +
              "inset 0 -2px 0 rgba(0, 0, 0, 0.30), " +
              "0 2px 0 rgba(0, 0, 0, 0.35), " +
              "0 6px 12px -4px rgba(0, 0, 0, 0.5), " +
              "0 0 0 1px rgba(58, 38, 28, 0.55)",
            textShadow: "0 1px 0 rgba(255, 240, 200, 0.5)",
          }}
          aria-label={`Hand value ${handValue}`}
        >
          {handValue}
        </span>
      )}
    </div>
  );
}
