/**
 * TableSeats.tsx — seated player chips.
 *
 * Each seat is a small "chip plaque" — engraved brass-trim card with
 * the username, seat #, chip balance, and current hand state. Current
 * user gets an amber edge ring and an inner candle highlight.
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
  active:    "text-saloon-amber",
  standing:  "text-saloon-ash",
  bust:      "text-saloon-blood",
  blackjack: "text-saloon-amber",
  finished:  "text-saloon-ash/60",
};

export default function TableSeats({ seats, hands, currentUserId }: TableSeatsProps) {
  if (seats.length === 0) {
    return (
      <div className="text-saloon-ash italic text-sm text-center py-4">
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
            className={`saloon-panel flex flex-col items-center gap-1.5 px-4 py-3
              rounded-md min-w-0 flex-1 chrome-in
              ${isMe ? "ring-2 ring-saloon-amber/70" : "ring-1 ring-saloon-brass/30"}`}
            style={{
              boxShadow: isMe
                ? "inset 0 1px 0 0 rgba(255,230,180,0.18), inset 0 -2px 0 0 rgba(0,0,0,0.35), 0 8px 24px -10px rgba(213,145,64,0.35)"
                : undefined,
            }}
          >
            <span
              className={`text-sm font-semibold truncate max-w-full tracking-wide
                ${isMe ? "text-saloon-amber" : "text-saloon-parchment"}`}
              style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}
            >
              {seat.username ?? t("Player")}
              {isMe && (
                <span className="ml-1 text-xs text-saloon-amber/70 italic">
                  {t("(you)")}
                </span>
              )}
            </span>

            <span className="text-[9px] uppercase tracking-[0.3em] text-saloon-ash">
              {t("Seat")} {seat.seat_number}
            </span>

            {seat.chip_balance !== null && (
              <span
                className="text-base font-bold"
                style={{
                  fontFamily: "'DM Serif Display', Georgia, serif",
                  color: "#d59140",
                  textShadow: "0 1px 0 rgba(0,0,0,0.6), 0 0 12px rgba(213,145,64,0.25)",
                }}
              >
                {formatCents(seat.chip_balance)}
              </span>
            )}

            {hand && (
              <span
                className={`text-[10px] font-bold uppercase tracking-widest
                  ${HAND_STATUS_COLORS[hand.status] ?? "text-saloon-parchment"}`}
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
