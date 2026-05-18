/**
 * useTablePoll.ts — 3-second polling of GET /api/tables/:id/state.
 *
 * Gold requirement: real-time-ish multiplayer via polling.
 * - Clears interval on unmount.
 * - Clears when session status is "finished".
 * - Pauses when tab is hidden (visibilityState === "hidden").
 * - Triggers gameStore.openChipy() when it becomes the user's turn.
 */
import { useEffect, useRef } from "react";
import { getTableState } from "../api/client";
import { useGameStore } from "../store/gameStore";

const POLL_INTERVAL_MS = 3000;

export function useTablePoll(tableId: string, currentUserId: string | null): void {
  const { reconcileFromPoll, openChipy } = useGameStore();

  // Track previous turn to detect change
  const prevMyTurnRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function poll(): Promise<void> {
      if (document.visibilityState === "hidden") return;

      const result = await getTableState(tableId);
      if (cancelled) return;
      if (result.error || result.data === null) return;

      const newState = result.data;
      reconcileFromPoll(newState, currentUserId ?? "");

      // Stop polling if session is finished
      if (newState.session?.status === "finished") {
        clearInterval(intervalId);
        return;
      }

      // Detect turn changes to open Chipy
      if (currentUserId) {
        const myHand = newState.hands.find((h) => h.user_id === currentUserId);
        const isMyTurn =
          newState.session?.status === "playing" &&
          myHand?.status === "active";

        // Non-trivial means not already blackjack or bust
        const isNonTrivial =
          myHand !== undefined &&
          myHand.status !== "blackjack" &&
          myHand.status !== "bust";

        if (isMyTurn && isNonTrivial && !prevMyTurnRef.current) {
          openChipy();
        }

        prevMyTurnRef.current = isMyTurn ?? false;
      }
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
  }, [tableId, currentUserId, reconcileFromPoll, openChipy]);
}
