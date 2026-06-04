/**
 * store/walletStore.ts — Zustand wallet store for the player's chip balance.
 *
 * Kept separate from gameStore so the cashier balance is a single coherent
 * source of truth across all pages and games.
 *
 * Contract (AC-F1):
 *   - balance: number | null  — null until the first successful fetch
 *   - loading: boolean        — true while a getMe() is in flight
 *   - error: string | null    — last error message; null when clean
 *   - refresh(): Promise<void> — calls getMe(), writes chip_balance on success;
 *       on error stores the message and PRESERVES any prior balance (no wipe)
 */
import { create } from "zustand";
import { getMe } from "../api/client";

interface WalletState {
  balance: number | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

// Monotonic token guarding against out-of-order responses. refresh() can be
// triggered concurrently (mount fetch + a post-mutation refresh, StrictMode
// double-invoke, rapid navigation). Without ordering, a slow earlier getMe()
// could resolve last and overwrite a newer, fresher balance with stale data.
// Each call captures the latest id; on return it only writes state if it is
// still the most-recently-started request.
let latestRequestId = 0;

export const useWalletStore = create<WalletState>((set, get) => ({
  balance: null,
  loading: false,
  error: null,

  async refresh(): Promise<void> {
    const requestId = (latestRequestId += 1);
    set({ loading: true });
    const { data, error } = await getMe();
    // A newer refresh() started while this one was in flight — drop this
    // (now stale) result so it cannot clobber the newer request's state.
    if (requestId !== latestRequestId) return;
    if (error) {
      // Keep any previously-loaded balance; only update error + loading.
      set({ loading: false, error });
    } else {
      set({
        balance: data?.chip_balance ?? get().balance,
        loading: false,
        error: null,
      });
    }
  },
}));
