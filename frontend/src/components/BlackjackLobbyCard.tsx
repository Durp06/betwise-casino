/**
 * BlackjackLobbyCard.tsx — entry point on the main lobby for Blackjack.
 *
 * Matches the Hold'em / Poker / Pai Gow cards so all four games read as one
 * consistent picker. Navigates to the Blackjack table browser at /blackjack.
 */
import { useNavigate } from "react-router-dom";
import { t } from "../i18n";

export default function BlackjackLobbyCard() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => void navigate("/blackjack")}
      className="w-full ink-outline-thick paper-grain rounded-md p-5 flex items-center gap-4 text-left
        hover:bg-gold-bright/20 transition-colors"
      style={{ backgroundColor: "#7B241C", boxShadow: "5px 5px 0 0 #1A0A00" }}
      data-testid="blackjack-lobby-card"
    >
      <span className="text-4xl" aria-hidden="true">♣️</span>
      <span className="flex flex-col">
        <span className="font-display text-cream text-2xl leading-tight">{t("Blackjack")}</span>
        <span className="font-flavor text-cream/70 text-sm italic">
          {t("Beat the dealer to 21 — Chipy coaches every hand.")}
        </span>
      </span>
    </button>
  );
}
