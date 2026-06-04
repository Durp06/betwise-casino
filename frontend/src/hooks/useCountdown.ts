/**
 * useCountdown.ts — a live seconds-remaining countdown against an absolute
 * server deadline (ISO-8601). The server is authoritative; the client only
 * renders the difference against its own wall clock, re-reading the (possibly
 * refreshed) deadline on every 3s poll.
 *
 * `secondsRemaining` is exported separately as a pure function so the math is
 * unit-testable without timers or React.
 */
import { useEffect, useState } from "react";

const TICK_MS = 250;

/** Whole seconds left until `deadlineIso`, or null when there is no deadline.
 *  Rounds up so the display shows "30" for the first fractional second and
 *  never dips to 0 before the deadline actually passes; floors at 0. */
export function secondsRemaining(
  deadlineIso: string | null,
  now: number = Date.now(),
): number | null {
  if (!deadlineIso) return null;
  const ms = Date.parse(deadlineIso) - now;
  return Math.max(0, Math.ceil(ms / 1000));
}

/** Re-renders ~4×/second with the seconds left until `deadlineIso`. Returns null
 *  when there is no deadline. Cleans up its interval on unmount / deadline change
 *  (StrictMode-safe). */
export function useCountdown(deadlineIso: string | null): number | null {
  const [remaining, setRemaining] = useState<number | null>(() => secondsRemaining(deadlineIso));

  useEffect(() => {
    setRemaining(secondsRemaining(deadlineIso));
    if (!deadlineIso) return;
    const id = setInterval(() => {
      setRemaining(secondsRemaining(deadlineIso));
    }, TICK_MS);
    return () => clearInterval(id);
  }, [deadlineIso]);

  return remaining;
}
