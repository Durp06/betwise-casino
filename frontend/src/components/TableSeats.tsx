/**
 * TableSeats.tsx — seat plaques shown across the top of the table.
 *
 * Each seat is a cream plaque with thick ink outline + offset shadow.
 * The current user gets a gold accent border.
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
  bust:      "Bust!",
  blackjack: "Blackjack!",
  finished:  "Done",
};

const HAND_STATUS_COLOR: Record<string, string> = {
  active:    "text-action-double",
  standing:  "text-ink/60",
  bust:      "text-action-hit",
  blackjack: "text-gold-dark",
  finished:  "text-ink/40",
};

export default function TableSeats({ seats, hands, currentUserId }: TableSeatsProps) {
  if (seats.length === 0) {
    return (
      <div className="font-flavor text-cream/60 italic text-sm text-center py-4">
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
            className={`ink-outline rounded-md px-4 py-3 flex flex-col items-center
              gap-1 flex-1 min-w-0 paper-grain`}
            style={{
              backgroundColor: "#F5F0E8",
              boxShadow: isMe
                ? "0 0 0 4px #F4D03F, 4px 4px 0 0 #1A0A00"
                : "3px 3px 0 0 #1A0A00",
            }}
          >
            <span className="font-ui text-ink text-sm truncate max-w-full">
              {seat.username ?? t("Player")}
              {isMe && (
                <span className="ml-1 text-xs text-ink/60">{t("(you)")}</span>
              )}
            </span>

            <span className="font-flavor text-ink/60 text-[10px] uppercase tracking-widest">
              {t("Seat")} {seat.seat_number}
            </span>

            {seat.chip_balance !== null && (
              <span className="font-display text-gold-dark text-lg leading-none">
                {formatCents(seat.chip_balance)}
              </span>
            )}

            {hand && (
              <span
                className={`font-ui uppercase tracking-wider text-[10px]
                  ${HAND_STATUS_COLOR[hand.status] ?? "text-ink"}`}
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
