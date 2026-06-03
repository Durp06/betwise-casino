/**
 * HandSetter.tsx — the tap-to-assign UI for the player's 2/5 split.
 *
 * Spec §AC-F3 + §15: pick exactly 2 cards for the FRONT; the remaining 5
 * auto-populate the back. Submit disabled until exactly 2 selected. Foul
 * preview (server-side validation surfaces 400; v1 doesn't compute foul
 * client-side).
 *
 * Mobile-first: 7 cards laid out in two rows (4+3) at phone width, tap
 * targets ≥ 44px.
 */
import { useState } from "react";
import { setPaiGowHand } from "../api/client";
import { usePaiGowStore } from "../store/paiGowStore";
import type { PaiGowCard, PaiGowPlayerHand } from "../types";
import PaiGowCardComp from "./PaiGowCard";
import { t } from "../i18n";

function cardKey(c: PaiGowCard): string {
  return `${c.suit}:${c.value}`;
}

interface Props {
  hand: PaiGowPlayerHand;
  onSubmitted: () => void;
}

export default function HandSetter({ hand, onSubmitted }: Props) {
  const { frontDraft, toggleFrontCard, clearFrontDraft, preOptimal } = usePaiGowStore();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dealt: PaiGowCard[] = (hand.dealt_cards ?? []) as PaiGowCard[];
  const isInFront = (c: PaiGowCard): boolean =>
    frontDraft.some((d) => cardKey(d) === cardKey(c));
  const back = dealt.filter((c) => !isInFront(c));
  const canSubmit = frontDraft.length === 2 && !submitting;

  // Highlight Chipy's recommended split if present.
  const recommendedKeys = new Set<string>(
    (preOptimal?.optimal_front ?? []).map(cardKey),
  );

  async function handleSubmit(): Promise<void> {
    if (!canSubmit) return;
    setError(null);
    setSubmitting(true);
    const res = await setPaiGowHand(hand.id, { front: frontDraft, back });
    setSubmitting(false);
    if (res.data === null) {
      setError(res.error);
      return;
    }
    clearFrontDraft();
    onSubmitted();
  }

  return (
    <section className="w-full" aria-label={t("Set your Pai Gow hand")}>
      <header className="mb-3">
        <h2 className="font-display text-cream text-2xl tracking-wider">
          {t("Set your hand")}
        </h2>
        <p className="font-flavor text-cream/70 text-sm italic">
          {t("Tap 2 cards for the front. The other 5 go to the back.")}
        </p>
      </header>

      {/* Dealt cards in a flexible grid. */}
      <div className="flex flex-wrap gap-2 justify-center mb-4">
        {dealt.map((c, i) => {
          const selected = isInFront(c);
          const recommended = recommendedKeys.has(cardKey(c));
          return (
            <button
              key={cardKey(c) + i}
              type="button"
              onClick={() => toggleFrontCard(c)}
              aria-pressed={selected}
              className={`min-h-[88px] min-w-[64px] transition-transform ${
                selected ? "translate-y-[-8px]" : ""
              } ${recommended && !selected ? "ring-2 ring-gold-bright rounded-md" : ""}`}
            >
              <PaiGowCardComp card={c} index={i} noAnimate />
            </button>
          );
        })}
      </div>

      <div className="text-cream text-center mb-3 font-ui text-sm">
        {t("Front")}: {frontDraft.length} / 2 — {t("Back")}: {back.length} / 5
      </div>

      {error !== null && (
        <p role="alert" className="text-red-300 text-center mb-3 font-ui text-sm">
          {error}
        </p>
      )}

      <div className="flex gap-2 justify-center">
        <button
          type="button"
          onClick={clearFrontDraft}
          disabled={frontDraft.length === 0 || submitting}
          className="px-4 py-3 rounded-md border-[3px] border-ink bg-cream text-ink
            font-ui uppercase text-sm disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {t("Clear")}
        </button>
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={!canSubmit}
          className="px-6 py-3 rounded-md border-[3px] border-ink bg-gold-bright text-ink
            font-ui uppercase tracking-widest disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {submitting ? t("Submitting…") : t("Set hand")}
        </button>
      </div>
    </section>
  );
}
