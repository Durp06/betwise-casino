/**
 * usePokerPoll.ts — 3-second poll of /api/poker/tournaments/{id}/state.
 *
 * Mirrors useTablePoll exactly — same cadence, same visibility-pause behavior.
 * The polling hook is the source of truth for the table state; the human
 * action submit (POST /act) returns the new state synchronously and the next
 * poll will pick up subsequent bot actions if any.
 */
import { useEffect } from "react";
import { getPokerTournamentState } from "../api/client";
import { useGameStore } from "../store/gameStore";

const POLL_INTERVAL_MS = 3000;

export function usePokerPoll(tournamentId: string): void {
  const setPokerTournamentState = useGameStore(
    (s) => s.setPokerTournamentState,
  );

  useEffect(() => {
    let cancelled = false;

    async function poll(): Promise<void> {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      const result = await getPokerTournamentState(tournamentId);
      if (cancelled) return;
      if (result.error || result.data === null) return;
      setPokerTournamentState(result.data);
    }

    void poll();
    const intervalId = setInterval(() => {
      void poll();
    }, POLL_INTERVAL_MS);

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
  }, [tournamentId, setPokerTournamentState]);
}
