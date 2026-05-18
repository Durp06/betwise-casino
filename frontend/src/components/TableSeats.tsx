/**
 * TableSeats.tsx — shows all seated players with chip counts and hand status.
 */
import type { Seat, Hand } from "../types";
import { t } from "../i18n";

interface TableSeatsProps {
  seats: Seat[];
  hands: Hand[];
  currentUserId: string | null;
}

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

const HAND_STATUS_LABELS: Record<string, string> = {
  active:    "Playing",
  standing:  "Standing",
  bust:      "Bust",
  blackjack: "Blackjack!",
  finished:  "Done",
};

const HAND_STATUS_COLORS: Record<string, string> = {
  active:    "text-green-400",
  standing:  "text-blue-400",
  bust:      "text-card-red",
  blackjack: "text-chip-gold",
  finished:  "text-white/60",
};

export default function TableSeats({ seats, hands, currentUserId }: TableSeatsProps) {
  if (seats.length === 0) {
    return (
      <div className="text-white/40 text-sm text-center py-4">
        {t("No players seated")}
      </div>
    );
  }

  return (
    <div className="flex flex-col sm:flex-row gap-3 w-full justify-center">
      {seats.map((seat) => {
        const hand = hands.find((h) => h.user_id === seat.user_id);
        const isMe = seat.user_id === currentUserId;

        return (
          <div
            key={seat.id}
            className={`flex flex-col items-center gap-1 p-3 rounded-lg border
              ${isMe ? "border-chip-gold bg-chip-gold/10" : "border-white/20 bg-white/5"}
              min-w-0 flex-1`}
          >
            <span className={`font-bold text-sm truncate max-w-full ${isMe ? "text-chip-gold" : "text-white"}`}>
              {seat.username ?? t("Player")}
              {isMe && <span className="ml-1 text-xs opacity-60">{t("(you)")}</span>}
            </span>
            <span className="text-xs text-white/60">
              {t("Seat")} {seat.seat_number}
            </span>
            {seat.chip_balance !== null && (
              <span className="text-xs font-medium text-green-400">
                {formatCents(seat.chip_balance)}
              </span>
            )}
            {hand && (
              <span
                className={`text-xs font-bold ${HAND_STATUS_COLORS[hand.status] ?? "text-white"}`}
              >
                {HAND_STATUS_LABELS[hand.status] ?? hand.status}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
