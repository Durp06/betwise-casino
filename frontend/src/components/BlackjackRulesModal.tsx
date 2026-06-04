/**
 * BlackjackRulesModal.tsx — short "How to Play" popup for Blackjack.
 *
 * A cream-paper plaque (matches the Cuphead/Vegas table aesthetic) with a
 * typewriter-font rule sheet. Dismissable four ways so it's never in the way:
 * the × button, the "Got it" button, clicking the backdrop, or pressing Escape.
 */
import { useEffect } from "react";
import { t } from "../i18n";

interface BlackjackRulesModalProps {
  onClose: () => void;
}

export default function BlackjackRulesModal({ onClose }: BlackjackRulesModalProps) {
  // Escape closes — paired with backdrop-click + the × / Got it buttons.
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
      aria-label={t("How to play Blackjack")}
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
            {t("How to Play Blackjack")}
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
            "Beat the dealer: land closer to 21 than they do without going over. Go over 21 and you bust — an instant loss.",
          )}
        </p>

        {/* How a round goes */}
        <section className="flex flex-col gap-1">
          <h3 className="font-ui uppercase tracking-widest text-xs text-ink/70">
            {t("How a round goes")}
          </h3>
          <ol className="font-flavor text-sm leading-relaxed list-decimal pl-5 flex flex-col gap-1">
            <li>{t("Place your bet. You and the dealer each get two cards — one dealer card stays face-down.")}</li>
            <li>{t("Number cards score their face value, J/Q/K score 10, and an ace is 1 or 11 — whichever helps.")}</li>
            <li>{t("Take your turn, then the dealer reveals the hole card and draws until at least 17.")}</li>
          </ol>
        </section>

        {/* Your moves */}
        <section className="flex flex-col gap-1">
          <h3 className="font-ui uppercase tracking-widest text-xs text-ink/70">
            {t("Your moves")}
          </h3>
          <ul className="font-flavor text-sm leading-relaxed flex flex-col gap-1">
            <li>
              <span className="font-ui uppercase text-xs">{t("Hit")}</span> — {t("take another card.")}
            </li>
            <li>
              <span className="font-ui uppercase text-xs">{t("Stand")}</span> — {t("keep your total and end your turn.")}
            </li>
            <li>
              <span className="font-ui uppercase text-xs">{t("Double")}</span> —{" "}
              {t("double the bet, take exactly one more card, then stand (first two cards only).")}
            </li>
          </ul>
        </section>

        {/* Payouts */}
        <section className="flex flex-col gap-1">
          <h3 className="font-ui uppercase tracking-widest text-xs text-ink/70">
            {t("Payouts")}
          </h3>
          <ul className="font-flavor text-sm leading-relaxed flex flex-col gap-1">
            <li>{t("Blackjack (an ace + a 10/face on your first two cards) pays 3:2.")}</li>
            <li>{t("Any other win pays even money (1:1); a tie pushes and your bet is returned.")}</li>
            <li>{t("The dealer hits on a soft 17.")}</li>
          </ul>
        </section>

        {/* Chipy's tip */}
        <p className="font-flavor text-sm leading-relaxed bg-ink/5 ink-outline rounded-lg p-3">
          <span className="font-ui uppercase text-xs tracking-widest text-ink/70">{t("Chipy's tip")}: </span>
          {t("When the dealer shows a weak upcard (2–6), stand on stiff totals (13–16) and let them risk the bust.")}
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
