/**
 * PaiGowRulesModal.tsx — short "How to Play" popup for Pai Gow Poker
 * (house-banked: split 7 cards into a 5-card back + 2-card front hand).
 *
 * Cream-paper plaque with typewriter rule copy. Dismissable four ways: the ×
 * button, the "Got it" button, a backdrop click, or the Escape key.
 */
import { useEffect } from "react";
import { t } from "../i18n";

interface PaiGowRulesModalProps {
  onClose: () => void;
}

export default function PaiGowRulesModal({ onClose }: PaiGowRulesModalProps) {
  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/70"
      role="dialog"
      aria-modal="true"
      aria-label={t("How to Play Pai Gow Poker")}
      onClick={onClose}
    >
      <div
        className="ink-outline-thick paper-grain rounded-2xl bg-cream text-ink
          w-full max-w-md max-h-[85vh] overflow-y-auto p-6 flex flex-col gap-4"
        style={{ boxShadow: "6px 6px 0 0 #1A0A00" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-display text-3xl tracking-wider text-ink leading-none">
            {t("How to Play Pai Gow Poker")}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("Close")}
            className="shrink-0 -mt-1 text-3xl leading-none text-ink/60 hover:text-ink"
          >
            ×
          </button>
        </div>

        {/* Goal */}
        <p className="font-flavor text-sm leading-relaxed">
          {t(
            "You're dealt seven cards and split them into two poker hands — a 5-card 'back' and a 2-card 'front'. Beat the dealer's two hands to win.",
          )}
        </p>

        {/* How a round goes */}
        <section className="flex flex-col gap-1">
          <h3 className="font-ui uppercase tracking-widest text-xs text-ink/70">
            {t("How a round goes")}
          </h3>
          <ol className="font-flavor text-sm leading-relaxed list-decimal pl-5 flex flex-col gap-1">
            <li>{t("Place your Ante (and an optional Fortune side bet). You're dealt seven cards.")}</li>
            <li>{t("Set them: five in the back, two in the front. The back must be the stronger hand — set it wrong (a 'foul') and you lose automatically.")}</li>
            <li>{t("The dealer sets their seven by a fixed house way, then compares front-to-front and back-to-back.")}</li>
          </ol>
        </section>

        {/* Win / push / loss */}
        <section className="flex flex-col gap-1">
          <h3 className="font-ui uppercase tracking-widest text-xs text-ink/70">
            {t("Win, push, or lose")}
          </h3>
          <ul className="font-flavor text-sm leading-relaxed flex flex-col gap-1">
            <li>{t("Win BOTH hands → you win (pays 1:1, no commission).")}</li>
            <li>{t("Win one, lose one → push (your bet comes back).")}</li>
            <li>{t("Win neither → you lose. Ties ('copies') go to the dealer.")}</li>
          </ul>
        </section>

        {/* Good to know */}
        <section className="flex flex-col gap-1">
          <h3 className="font-ui uppercase tracking-widest text-xs text-ink/70">
            {t("Good to know")}
          </h3>
          <ul className="font-flavor text-sm leading-relaxed flex flex-col gap-1">
            <li>{t("The joker is semi-wild: it plays as an ace, or completes a straight or flush.")}</li>
            <li>{t("Your two-card front can only be a pair or high cards — no straights or flushes.")}</li>
            <li>{t("The optional Fortune side bet pays on three-of-a-kind or better in your seven cards.")}</li>
          </ul>
        </section>

        {/* Chipy's tip */}
        <p className="font-flavor text-sm leading-relaxed bg-ink/5 ink-outline rounded-lg p-3">
          <span className="font-ui uppercase text-xs tracking-widest text-ink/70">{t("Chipy's tip")}: </span>
          {t("Keep the back hand strong — it decides most rounds; the front is where your weakest playable cards go.")}
        </p>

        <button
          type="button"
          onClick={onClose}
          className="ink-outline ink-shadow self-end rounded-md bg-gold-bright text-ink
            font-ui uppercase tracking-widest text-sm px-5 py-3 min-h-[48px]"
        >
          {t("Got it")}
        </button>
      </div>
    </div>
  );
}
