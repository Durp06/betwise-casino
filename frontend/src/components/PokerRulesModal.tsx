/**
 * PokerRulesModal.tsx — short "How to Play" popup for the Solo Poker Trainer
 * (single-table No-Limit Texas Hold'em sit-and-go against bots).
 *
 * Cream-paper plaque with typewriter rule copy. Dismissable four ways: the ×
 * button, the "Got it" button, a backdrop click, or the Escape key.
 */
import { useEffect } from "react";
import ModalShell from "../motion/presence/ModalShell";
import { t } from "../i18n";

interface PokerRulesModalProps {
  onClose: () => void;
}

export default function PokerRulesModal({ onClose }: PokerRulesModalProps) {
  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <ModalShell
      onClose={onClose}
      ariaLabel={t("How to Play Texas Hold'em")}
      panelClassName="ink-outline-thick paper-grain rounded-2xl bg-cream text-ink w-full max-w-md max-h-[85vh] overflow-y-auto p-6 flex flex-col gap-4 shadow-[6px_6px_0_0_#1A0A00]"
    >
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-display text-3xl tracking-wider text-ink leading-none">
            {t("How to Play Texas Hold'em")}
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
            "Outlast 2–7 bots in a single-table No-Limit sit-and-go. Win chips hand by hand until you're the last player standing — Chipy coaches every decision.",
          )}
        </p>

        {/* How a hand goes */}
        <section className="flex flex-col gap-1">
          <h3 className="font-ui uppercase tracking-widest text-xs text-ink/70">
            {t("How a hand goes")}
          </h3>
          <ol className="font-flavor text-sm leading-relaxed list-decimal pl-5 flex flex-col gap-1">
            <li>{t("Blinds are posted, and everyone is dealt two private hole cards.")}</li>
            <li>{t("Bet pre-flop, then after the flop (3 shared cards), the turn (1), and the river (1).")}</li>
            <li>{t("At showdown, make your best five-card hand from your two cards plus the five on the board.")}</li>
          </ol>
        </section>

        {/* Your moves */}
        <section className="flex flex-col gap-1">
          <h3 className="font-ui uppercase tracking-widest text-xs text-ink/70">
            {t("Your moves")}
          </h3>
          <ul className="font-flavor text-sm leading-relaxed flex flex-col gap-1">
            <li>
              <span className="font-ui uppercase text-xs">{t("Fold")}</span> — {t("give up the hand.")}
            </li>
            <li>
              <span className="font-ui uppercase text-xs">{t("Check")}</span> — {t("pass when no bet faces you.")}
            </li>
            <li>
              <span className="font-ui uppercase text-xs">{t("Call")}</span> — {t("match the current bet.")}
            </li>
            <li>
              <span className="font-ui uppercase text-xs">{t("Raise")}</span> —{" "}
              {t("put in more (at least the last raise, or the big blind).")}
            </li>
            <li>
              <span className="font-ui uppercase text-xs">{t("All-in")}</span> —{" "}
              {t("push your whole stack; side pots form if others have more.")}
            </li>
          </ul>
        </section>

        {/* Hand rankings */}
        <section className="flex flex-col gap-1">
          <h3 className="font-ui uppercase tracking-widest text-xs text-ink/70">
            {t("Hand ranks (high to low)")}
          </h3>
          <p className="font-flavor text-sm leading-relaxed">
            {t(
              "Straight flush ▸ Four of a kind ▸ Full house ▸ Flush ▸ Straight ▸ Three of a kind ▸ Two pair ▸ Pair ▸ High card.",
            )}
          </p>
        </section>

        {/* Key rules */}
        <section className="flex flex-col gap-1">
          <h3 className="font-ui uppercase tracking-widest text-xs text-ink/70">
            {t("Good to know")}
          </h3>
          <ul className="font-flavor text-sm leading-relaxed flex flex-col gap-1">
            <li>{t("Winner-take-all: only first place wins the buy-in pool.")}</li>
            <li>{t("Blinds rise every 10 hands, so stalling slowly bleeds your stack.")}</li>
          </ul>
        </section>

        {/* Chipy's tip */}
        <p className="font-flavor text-sm leading-relaxed bg-ink/5 ink-outline rounded-lg p-3">
          <span className="font-ui uppercase text-xs tracking-widest text-ink/70">{t("Chipy's tip")}: </span>
          {t("Position pays — play tight from early seats and open up when you're last to act.")}
        </p>

        <button
          type="button"
          onClick={onClose}
          className="ink-outline ink-shadow self-end rounded-md bg-gold-bright text-ink
            font-ui uppercase tracking-widest text-sm px-5 py-3 min-h-[48px]"
        >
          {t("Got it")}
        </button>
    </ModalShell>
  );
}
