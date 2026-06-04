/**
 * MoveTimer.tsx — a small countdown badge shown on the seat of whoever is on the
 * clock. Reads the server-authoritative `move_deadline_at` and ticks down,
 * shifting green → amber → red as the deadline approaches. Renders nothing when
 * there is no deadline (nobody on the clock / not this seat's turn).
 */
import { useCountdown } from "../hooks/useCountdown";
import { t } from "../i18n";

interface MoveTimerProps {
  deadlineAt: string | null;
}

export default function MoveTimer({ deadlineAt }: MoveTimerProps) {
  const seconds = useCountdown(deadlineAt);
  if (seconds === null) return null;

  const tone =
    seconds > 15 ? "text-action-stand" : seconds > 5 ? "text-gold-bright" : "text-action-hit";

  return (
    <span
      role="timer"
      aria-label={t("Time remaining to act")}
      className={`font-display text-sm tabular-nums ${tone} ${seconds <= 5 ? "animate-pulse" : ""}`}
      data-testid="move-timer"
    >
      {seconds}s
    </span>
  );
}
