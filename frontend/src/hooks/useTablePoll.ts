/**
 * useTablePoll.ts — 3-second polling of GET /api/tables/:id/state.
 *
 * Gold requirement: real-time-ish multiplayer via polling.
 * - Clears interval on unmount.
 * - Pauses when tab is hidden (visibilityState === "hidden").
 * - Continues across "finished" so the next Deal picks up the new session.
 *
 * Chipy triggers (pre-play / post-play) live in Table.tsx and ActionBar.tsx
 * respectively — the polling hook stays pure state-reconciliation.
 */
import { useEffect, useRef } from "react";
import { getTableState } from "../api/client";
import { useGameStore } from "../store/gameStore";

const POLL_INTERVAL_MS = 3000;
/** Number of consecutive failures before calling onError. */
const ERROR_THRESHOLD = 3;

export function useTablePoll(
  tableId: string,
  currentUserId: string | null,
  onError?: (msg: string) => void,
): void {
  const { reconcileFromPoll } = useGameStore();
  const failureCount = useRef(0);

  useEffect(() => {
    let cancelled = false;

    async function poll(): Promise<void> {
      if (document.visibilityState === "hidden") return;

      const result = await getTableState(tableId);
      if (cancelled) return;
      if (result.error || result.data === null) {
        failureCount.current += 1;
        if (failureCount.current >= ERROR_THRESHOLD && onError) {
          onError(result.error ?? "Failed to load table state");
        }
        return;
      }

      // Successful poll — reset failure counter.
      failureCount.current = 0;
      reconcileFromPoll(result.data, currentUserId ?? "");
    }

    // Poll immediately on mount, then on interval
    void poll();
    const intervalId = setInterval(() => { void poll(); }, POLL_INTERVAL_MS);

    // Visibility change handler
    function handleVisibilityChange(): void {
      if (document.visibilityState === "visible") {
        void poll();
      }
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [tableId, currentUserId, reconcileFromPoll, onError]);
}
