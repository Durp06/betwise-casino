/**
 * useHoldemPoll.ts — 3-second polling of GET /api/holdem/tables/:id/state.
 *
 * Mirrors useTablePoll: clears the interval on unmount, pauses while the tab is
 * hidden, and re-polls immediately when it becomes visible again. Other humans'
 * actions arrive on the same 3s cadence — this is the multiplayer sync.
 */
import { useEffect, useRef } from "react";
import { getHoldemTableState } from "../api/client";
import { useGameStore } from "../store/gameStore";

const POLL_INTERVAL_MS = 3000;
/** Number of consecutive failures before calling onError. */
const ERROR_THRESHOLD = 3;

export function useHoldemPoll(tableId: string, onError?: (msg: string) => void): void {
  const setHoldemTableState = useGameStore((s) => s.setHoldemTableState);
  const failureCount = useRef(0);

  useEffect(() => {
    let cancelled = false;

    async function poll(): Promise<void> {
      if (document.visibilityState === "hidden") return;
      const result = await getHoldemTableState(tableId);
      if (cancelled) return;
      if (result.error || result.data === null) {
        failureCount.current += 1;
        if (failureCount.current >= ERROR_THRESHOLD && onError) {
          onError(result.error ?? "Failed to load table state");
        }
        return;
      }
      failureCount.current = 0;
      setHoldemTableState(result.data);
    }

    void poll();
    const intervalId = setInterval(() => { void poll(); }, POLL_INTERVAL_MS);

    function handleVisibilityChange(): void {
      if (document.visibilityState === "visible") void poll();
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [tableId, setHoldemTableState, onError]);
}
