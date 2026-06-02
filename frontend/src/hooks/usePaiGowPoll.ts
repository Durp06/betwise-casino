/**
 * hooks/usePaiGowPoll.ts — 3-second polling for the Pai Gow table state.
 *
 * Mirrors `useTablePoll` (blackjack) at the API surface level but operates on
 * the separate PG endpoint + store. Each poll:
 *   1. fetches `/api/pai-gow/tables/{id}/state`
 *   2. on success, pushes the response into `usePaiGowStore` via setTableState
 *   3. on error, surfaces via the `error` return so the page can render an
 *      error state without breaking the polling cadence.
 *
 * Pause / resume behavior:
 *   - Pauses when the browser tab is hidden (visibilitychange).
 *   - In-flight guard via a ref so a slow fetch + a tick don't stack.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { getPaiGowTableState } from "../api/client";
import { usePaiGowStore } from "../store/paiGowStore";

const POLL_INTERVAL_MS = 3_000;

export function usePaiGowPoll(
  tableId: string | null,
  currentUserId: string,
): { error: string | null; refetch: () => Promise<void> } {
  const setTableState = usePaiGowStore((s) => s.setTableState);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const isMounted = useRef(true);

  const fetchOnce = useCallback(async (): Promise<void> => {
    if (!tableId) return;
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const res = await getPaiGowTableState(tableId);
      if (!isMounted.current) return;
      if (res.data === null) {
        // Narrow via data → ApiResult's discriminated union means error is non-null here.
        setError(res.error);
        return;
      }
      setError(null);
      setTableState(res.data, currentUserId);
    } finally {
      inFlight.current = false;
    }
  }, [tableId, currentUserId, setTableState]);

  useEffect(() => {
    isMounted.current = true;
    if (!tableId) return;

    // Fire immediately on mount.
    void fetchOnce();

    let intervalId: number | undefined;

    function startPolling(): void {
      if (intervalId !== undefined) return;
      intervalId = window.setInterval(() => {
        if (document.visibilityState === "visible") {
          void fetchOnce();
        }
      }, POLL_INTERVAL_MS);
    }
    function stopPolling(): void {
      if (intervalId !== undefined) {
        window.clearInterval(intervalId);
        intervalId = undefined;
      }
    }
    function onVisibilityChange(): void {
      if (document.visibilityState === "visible") {
        void fetchOnce();
        startPolling();
      } else {
        stopPolling();
      }
    }

    startPolling();
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      isMounted.current = false;
      stopPolling();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [tableId, fetchOnce]);

  return { error, refetch: fetchOnce };
}
