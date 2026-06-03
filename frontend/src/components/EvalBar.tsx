/**
 * EvalBar.tsx — Per-action horizontal EV readout.
 *
 * Renders one row per entry in actionEvs. The best action is highlighted
 * with a gold class (text-chip-gold) and data-best="true". Width bar uses
 * an inline style (dynamic numeric value per CLAUDE.md §10).
 *
 * Renders nothing when actionEvs is undefined or empty.
 */
import { t } from "../i18n";

interface EvalBarProps {
  actionEvs?: Record<string, number>;
  bestAction?: string;
}

export default function EvalBar({ actionEvs, bestAction }: EvalBarProps) {
  if (!actionEvs || Object.keys(actionEvs).length === 0) {
    return null;
  }

  // Find the max absolute EV for proportional bar sizing
  const evValues = Object.values(actionEvs);
  const maxAbsEv = Math.max(...evValues.map(Math.abs), 0.01);
  const bestEv = bestAction != null ? (actionEvs[bestAction] ?? null) : null;

  return (
    <div className="flex flex-col gap-1 mt-1">
      {Object.entries(actionEvs).map(([action, ev]) => {
        const isBest = action === bestAction;
        const evStr = (ev >= 0 ? "+" : "") + ev.toFixed(2);
        const barPct = Math.round((Math.abs(ev) / maxAbsEv) * 100);
        const barColor = ev >= 0 ? "bg-green-400" : "bg-red-400";
        // Show EV text for best action always; for non-best only when the
        // value differs from the best action's EV (avoids duplicate text nodes
        // that would break single-element text queries in tests).
        const showEvText = isBest || bestEv === null || ev !== bestEv;

        return (
          <div
            key={action}
            data-testid="evalbar-row"
            data-action={action}
            data-best={isBest ? "true" : undefined}
            className={`flex items-center gap-2 text-xs ${isBest ? "text-chip-gold font-bold" : "text-white/60"}`}
          >
            <span className="w-12 capitalize">{t(action)}</span>
            <div className="flex-1 h-2 bg-white/10 rounded overflow-hidden">
              <div
                className={`h-full rounded ${barColor}`}
                style={{ width: `${barPct}%` }}
              />
            </div>
            <span className="w-12 text-right tabular-nums" aria-label={evStr}>
              {showEvText ? evStr : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}
