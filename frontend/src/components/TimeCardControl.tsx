/**
 * TimeCardControl.tsx — Hold'em time cards. Shows how many of the player's 5
 * time cards remain and a "+15s" button to spend one (extending the current move
 * clock). Shown only on the player's own turn; disabled when depleted or while a
 * use is in flight.
 */
import { t } from "../i18n";

const MAX_TIME_CARDS = 5;

interface TimeCardControlProps {
  remaining: number;
  onUse: () => void;
  busy?: boolean;
}

export default function TimeCardControl({ remaining, onUse, busy = false }: TimeCardControlProps) {
  const depleted = remaining <= 0;
  return (
    <div className="flex items-center gap-2" data-testid="time-card-control">
      <span className="font-ui text-cream/80 text-xs uppercase tracking-wider">
        {t("Time cards")} {remaining}/{MAX_TIME_CARDS}
      </span>
      <button
        type="button"
        disabled={depleted || busy}
        onClick={onUse}
        aria-busy={busy}
        className="px-3 py-1 font-ui text-xs rounded ink-outline ink-shadow bg-gold-bright text-ink disabled:opacity-40"
        data-testid="time-card-use"
        title={t("Spend a time card to add 15 seconds to your clock")}
      >
        {busy ? t("…") : t("+15s")}
      </button>
    </div>
  );
}
