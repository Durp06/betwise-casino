/**
 * hooks/useBalance.ts — thin hook wrapping the wallet Zustand store.
 *
 * Returns { balance, loading, error, refresh } backed by useWalletStore.
 * Components should call refresh() on mount and after money-moving mutations.
 */
import { useWalletStore } from "../store/walletStore";

export interface BalanceHook {
  balance: number | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useBalance(): BalanceHook {
  const balance = useWalletStore((s) => s.balance);
  const loading = useWalletStore((s) => s.loading);
  const error = useWalletStore((s) => s.error);
  const refresh = useWalletStore((s) => s.refresh);
  return { balance, loading, error, refresh };
}
