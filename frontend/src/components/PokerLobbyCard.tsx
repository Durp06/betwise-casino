/**
 * PokerLobbyCard.tsx — entry point for Texas Hold'em from the main Lobby.
 *
 * Click → navigates to /poker/setup where the user picks bot count + mode +
 * buy-in.
 */
import { useNavigate } from "react-router-dom";
import { t } from "../i18n";

export default function PokerLobbyCard() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => void navigate("/poker/setup")}
      className="w-full ink-outline-thick paper-grain rounded-md p-5 flex items-center gap-4 text-left
        hover:bg-gold-bright/20 transition-colors"
      style={{ backgroundColor: "#145A32", boxShadow: "5px 5px 0 0 #1A0A00" }}
      data-testid="poker-lobby-card"
    >
      <span className="text-4xl" aria-hidden="true">♥️</span>
      <span className="flex flex-col">
        <span className="flex items-center gap-2 flex-wrap">
          <span className="font-display text-cream text-2xl leading-tight">{t("Solo Poker Trainer")}</span>
          <span className="text-[10px] uppercase tracking-widest bg-gold-bright text-ink px-2 py-0.5 rounded-full border-2 border-ink">
            {t("Educational")}
          </span>
        </span>
        <span className="font-flavor text-cream/70 text-sm italic">
          {t("Single-table tournament against 2–7 bot archetypes. Chipy coaches every decision.")}
        </span>
      </span>
    </button>
  );
}
