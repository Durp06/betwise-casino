/**
 * PaiGowSeat.tsx — single-seat display with username + chip balance.
 */
import type { PaiGowSeat as PaiGowSeatType } from "../types";
import { t } from "../i18n";
import { formatMoney } from "../utils/money";

interface Props {
  seat: PaiGowSeatType | null;
  seatNumber: number;
  isCurrentUser?: boolean;
}

export default function PaiGowSeat({ seat, seatNumber, isCurrentUser = false }: Props) {
  if (seat === null) {
    return (
      <div
        className="ink-outline-thick rounded-md p-2 min-w-[100px] text-center
          bg-cream/30 text-cream/60 font-ui text-xs"
      >
        {t("Seat")} {seatNumber}<br />
        {t("(open)")}
      </div>
    );
  }
  return (
    <div
      className={`ink-outline-thick rounded-md p-2 min-w-[100px] text-center
        bg-cream text-ink font-ui text-xs ${isCurrentUser ? "ring-2 ring-gold-bright" : ""}`}
    >
      <div className="font-display text-base truncate">{seat.username ?? "?"}</div>
      {seat.chip_balance !== null && (
        <div className="tabular-nums text-[10px]">{formatMoney(seat.chip_balance)}</div>
      )}
      {isCurrentUser && (
        <div className="text-[9px] uppercase tracking-widest mt-1">{t("You")}</div>
      )}
    </div>
  );
}
