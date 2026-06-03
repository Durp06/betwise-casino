/**
 * FortunePoolTicker.tsx — top-of-table animated counter for the Fortune
 * progressive pool. Reads from `tableState.fortune_pool_amount_cents`
 * (the polled state already includes the pool snapshot inline).
 */
import { usePaiGowStore } from "../store/paiGowStore";
import { t } from "../i18n";

function formatDollars(cents: number): string {
  const dollars = cents / 100;
  return dollars.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function FortunePoolTicker() {
  const tableState = usePaiGowStore((s) => s.tableState);
  const amount = tableState?.fortune_pool_amount_cents ?? 0;

  return (
    <div
      className="ink-outline-thick rounded-md px-3 py-2 inline-flex flex-col items-center
        bg-gold-bright text-ink"
      style={{ boxShadow: "3px 3px 0 0 #1A0A00" }}
      aria-label={t("Fortune progressive pool")}
    >
      <span className="font-ui text-[10px] uppercase tracking-widest">
        {t("Fortune Pool")}
      </span>
      <span className="font-display text-2xl tracking-wider tabular-nums">
        {formatDollars(amount)}
      </span>
    </div>
  );
}
