/**
 * PaiGowLobbyCard.tsx — entry point on the main lobby for Pai Gow Poker.
 *
 * Matches the Blackjack / Hold'em / Poker cards so all four games read as one
 * consistent picker. Navigates to the Pai Gow table browser at /pai-gow/lobby.
 */
import { useNavigate } from "react-router-dom";
import { t } from "../i18n";

export default function PaiGowLobbyCard() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => void navigate("/pai-gow/lobby")}
      className="w-full ink-outline-thick paper-grain rounded-md p-5 flex items-center gap-4 text-left
        hover:bg-gold-bright/20 transition-colors"
      style={{ backgroundColor: "#1B4F72", boxShadow: "5px 5px 0 0 #1A0A00" }}
      data-testid="paigow-lobby-card"
    >
      <span className="text-4xl" aria-hidden="true">♦️</span>
      <span className="flex flex-col">
        <span className="font-display text-cream text-2xl leading-tight">{t("Pai Gow Poker")}</span>
        <span className="font-flavor text-cream/70 text-sm italic">
          {t("Set a high hand and a low hand to beat the banker — Fortune bonus in play.")}
        </span>
      </span>
    </button>
  );
}
