/**
 * PotDisplay.tsx — shows the main pot and any side pots.
 *
 * When there's only one pot, shows "Pot: N". When side pots exist, lists
 * each pot with its amount and the seat-number eligibility set.
 */
import { t } from "../i18n";

interface SidePot {
  amount: number;
  eligible: number[];
}

interface PotDisplayProps {
  potTotal: number;
  sidePots: SidePot[];
}

export default function PotDisplay({ potTotal, sidePots }: PotDisplayProps) {
  // Hide structured side pots once the hand is settled (potTotal == 0)
  const showSidePots = sidePots && sidePots.length > 1;
  return (
    <div className="flex flex-col items-center gap-1" data-testid="pot-display">
      <div className="text-xl font-ui text-cream bg-ink px-3 py-1 rounded">
        {t("Pot")}: {potTotal}
      </div>
      {showSidePots && (
        <div className="flex flex-col gap-0.5 text-xs font-mono text-cream">
          {sidePots.map((p, idx) => (
            <div key={idx} data-testid={`side-pot-${idx}`}>
              {idx === 0 ? t("Main") : `${t("Side")} ${idx}`}: {p.amount} →{" "}
              {p.eligible.map((s) => `s${s}`).join(",")}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
