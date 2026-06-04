/**
 * PaiGowResultView.tsx — post-resolve comparison panel.
 *
 * Renders Dealer and You side-by-side, each split into Front (2) + Back (5),
 * plus the per-side outcome chip (WON / LOST / COPY → DEALER) on the player's
 * columns so the player can read why they won, pushed, or lost. The verdict
 * and Ante / Fortune payouts ride at the top; a short explainer line at the
 * bottom teaches the both-sides-must-win rule.
 *
 * All data is already on the polled state — see PaiGowRound (dealer_front /
 * dealer_back) and PaiGowPlayerHand (front_cards / back_cards /
 * front_compare / back_compare / hand_result / *_payout_cents).
 */
import type {
  PaiGowHandResult,
  PaiGowPlayerHand,
  PaiGowRound,
  PaiGowSideCompare,
} from "../types";
import PaiGowCardComp from "./PaiGowCard";
import { t } from "../i18n";
import { formatMoney } from "../utils/money";

interface Props {
  round: PaiGowRound;
  myHand: PaiGowPlayerHand;
}

function formatDollars(cents: number | null): string {
  if (cents === null) return "—";
  const sign = cents > 0 ? "+" : cents < 0 ? "-" : "";
  return `${sign}${formatMoney(Math.abs(cents))}`;
}

function sideLabel(compare: PaiGowSideCompare | null): string {
  if (compare === "player") return t("Won");
  if (compare === "banker") return t("Lost");
  if (compare === "copy") return t("Copy → dealer");
  return "";
}

function sideTagClass(compare: PaiGowSideCompare | null): string {
  const base =
    "px-2 py-0.5 rounded font-ui text-[10px] uppercase tracking-widest";
  if (compare === "player") return `${base} bg-action-stand text-cream`;
  if (compare === "banker") return `${base} bg-action-hit text-cream`;
  if (compare === "copy") return `${base} bg-gold-mid text-ink`;
  return base;
}

function explainerText(handResult: PaiGowHandResult | null): string {
  if (handResult === "win") return t("Both sides won — you collect.");
  if (handResult === "push") return t("Won one, lost one — push.");
  if (handResult === "lose") return t("Lost both — dealer wins.");
  return "";
}

function verdictHeading(handResult: PaiGowHandResult | null): string {
  if (handResult === "win") return t("You win!");
  if (handResult === "push") return t("Push");
  if (handResult === "lose") return t("Dealer wins");
  return "";
}

export default function PaiGowResultView({ round, myHand }: Props) {
  return (
    <div
      className="ink-outline-thick rounded-xl p-4 bg-cream text-ink space-y-4"
      data-testid="pai-gow-result-view"
    >
      {/* Verdict + payouts */}
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-display text-2xl tracking-wider">
          {verdictHeading(myHand.hand_result)}
        </h3>
        <p className="font-ui text-sm tabular-nums">
          {t("Ante")}: {formatDollars(myHand.ante_payout_cents)}
          {myHand.fortune_payout_cents !== null && (
            <>
              {" · "}
              {t("Fortune")}: {formatDollars(myHand.fortune_payout_cents)}
            </>
          )}
        </p>
      </div>

      {/* Side-by-side comparison.
          `md:` (≥768px) — not `sm:` (≥640px) — so the two columns stack
          vertically on phones. A side-by-side grid at 640px squeezes the
          5-card back row below the available width (~311px usable on
          iPhone SE, ~326px on iPhone 13) and forces a 3+2 wrap. Stacked
          single-column gives each row the full phone width. */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* DEALER column */}
        <div className="space-y-3" data-testid="result-dealer-column">
          <h4 className="font-display text-sm tracking-widest uppercase text-ink/70">
            {t("Dealer")}
          </h4>
          <div>
            <div className="font-ui text-[10px] uppercase tracking-widest text-ink/60 mb-1">
              {t("Front")}
            </div>
            <div className="flex gap-1" data-testid="dealer-front">
              {round.dealer_front?.map((c, i) => (
                <PaiGowCardComp key={`df${i}`} card={c} index={i} noAnimate />
              ))}
            </div>
          </div>
          <div>
            <div className="font-ui text-[10px] uppercase tracking-widest text-ink/60 mb-1">
              {t("Back")}
            </div>
            <div className="flex flex-wrap gap-1" data-testid="dealer-back">
              {round.dealer_back?.map((c, i) => (
                <PaiGowCardComp key={`db${i}`} card={c} index={i} noAnimate />
              ))}
            </div>
          </div>
        </div>

        {/* YOU column — per-side outcome chips */}
        <div className="space-y-3" data-testid="result-you-column">
          <h4 className="font-display text-sm tracking-widest uppercase text-ink/70">
            {t("You")}
          </h4>
          <div>
            <div className="font-ui text-[10px] uppercase tracking-widest text-ink/60 mb-1 flex items-center gap-2">
              {t("Front")}
              <span
                className={sideTagClass(myHand.front_compare)}
                data-testid="player-front-chip"
              >
                {sideLabel(myHand.front_compare)}
              </span>
            </div>
            <div className="flex gap-1" data-testid="player-front">
              {myHand.front_cards?.map((c, i) => (
                <PaiGowCardComp key={`pf${i}`} card={c} index={i} noAnimate />
              ))}
            </div>
          </div>
          <div>
            <div className="font-ui text-[10px] uppercase tracking-widest text-ink/60 mb-1 flex items-center gap-2">
              {t("Back")}
              <span
                className={sideTagClass(myHand.back_compare)}
                data-testid="player-back-chip"
              >
                {sideLabel(myHand.back_compare)}
              </span>
            </div>
            <div className="flex flex-wrap gap-1" data-testid="player-back">
              {myHand.back_cards?.map((c, i) => (
                <PaiGowCardComp key={`pb${i}`} card={c} index={i} noAnimate />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Explainer — teaches the both-sides-must-win rule */}
      <p className="font-flavor italic text-xs text-ink/70">
        {explainerText(myHand.hand_result)}
      </p>
    </div>
  );
}
