/**
 * components/BalanceHeader.tsx — persistent balance display.
 *
 * Calls refresh() on mount (AC-F5), then renders:
 *   - formatMoney(balance) when balance is loaded (AC-F2)
 *   - role="status" skeleton while loading and balance is null (AC-F3)
 *   - role="alert" error badge when error and balance is null (AC-F3)
 *
 * All user-facing text goes through t() (AC-F9). Tailwind only (AC-F7).
 */
import { useEffect, useRef } from "react";
import { useBalance } from "../hooks/useBalance";
import { formatMoney } from "../utils/money";
import { t } from "../i18n";

export default function BalanceHeader() {
  const { balance, loading, error, refresh } = useBalance();
  const didFetch = useRef(false);

  useEffect(() => {
    // Fetch once on mount when there is no balance and no prior error. If an
    // error is already stored (a prior failed fetch) we leave it displayed; the
    // next mount or a mutation-triggered refresh will retry.
    //
    // The didFetch ref makes this idempotent under React.StrictMode's dev-only
    // setup→cleanup→setup double-invoke: the store's loading flag isn't visible
    // to the second invocation's stale closure, so a value guard alone would
    // still double-fire. The ref persists across the double-invoke on the same
    // instance, guaranteeing a single GET /api/users/me per mount.
    if (didFetch.current) return;
    if (balance === null && !error) {
      didFetch.current = true;
      void refresh();
    }
    // refresh identity is stable (Zustand getter); balance/error intentionally
    // not in deps — this should only fire once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading && balance === null) {
    return (
      <span
        role="status"
        aria-busy="true"
        className="font-ui text-cream/60 text-sm animate-pulse px-3 py-1"
      >
        {t("Loading balance…")}
      </span>
    );
  }

  if (error && balance === null) {
    return (
      <span
        role="alert"
        className="font-ui text-action-hit text-sm px-3 py-1"
      >
        {t("Balance unavailable")}
      </span>
    );
  }

  if (balance !== null) {
    return (
      <span className="font-display text-gold-bright text-base px-3 py-1 tabular-nums">
        {formatMoney(balance)}
      </span>
    );
  }

  return null;
}
