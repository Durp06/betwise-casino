/**
 * HoldemLobbyCard.tsx — entry point on the main lobby for multiplayer
 * Texas Hold'em. Navigates to the Hold'em table browser at /holdem.
 */
import { useNavigate } from "react-router-dom";
import { t } from "../i18n";

export default function HoldemLobbyCard() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => void navigate("/holdem")}
      className="w-full ink-outline-thick paper-grain rounded-md p-5 flex items-center gap-4 text-left hover:bg-gold-bright/20"
      style={{ backgroundColor: "#0D3B1F", boxShadow: "5px 5px 0 0 #1A0A00" }}
      data-testid="holdem-lobby-card"
    >
      <span className="text-4xl" aria-hidden="true">♠️</span>
      <span className="flex flex-col">
        <span className="font-display text-cream text-2xl leading-tight">
          {t("Multiplayer Hold'em")}
        </span>
        <span className="font-flavor text-cream/70 text-sm italic">
          {t("Sit down at a live cash table — real players, real blinds.")}
        </span>
      </span>
    </button>
  );
}
