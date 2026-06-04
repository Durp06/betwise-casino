/**
 * DeckStack — the visible deck (a small fanned stack of card backs) that cards
 * are dealt from. Registers its DOM node into DeckProvider so DealtCard can fly
 * from it. Render one per felt; the `className` positions the outer node (the
 * inner holds the fan so callers can position it absolutely without a conflict).
 */
import { useDeckContext } from "../motion/DeckProvider";
import { t } from "../i18n";

export default function DeckStack({ className = "" }: { className?: string }) {
  const ctx = useDeckContext();
  return (
    <div
      ref={(el) => {
        if (ctx) ctx.deckRef.current = el;
      }}
      aria-label={t("Deck")}
      className={`w-16 h-24 sm:w-20 sm:h-28 ${className}`}
    >
      <div className="relative w-full h-full wobble">
        {[2, 1, 0].map((i) => (
          <div
            key={i}
            className="card-back-pattern ink-outline-thick w-full h-full rounded-md absolute inset-0"
            style={{
              transform: `translate(${i * 1.5}px, ${-i * 1.5}px) rotate(${i * 1.5}deg)`,
              boxShadow: "3px 3px 0 0 #1A0A00",
            }}
          >
            <div className="absolute inset-1 rounded-sm border-2 border-cream/70" />
          </div>
        ))}
      </div>
    </div>
  );
}
