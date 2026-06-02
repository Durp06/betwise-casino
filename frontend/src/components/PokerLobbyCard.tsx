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
      className="ink-outline-thick rounded-xl bg-felt-green text-cream p-4 flex flex-col items-start gap-2 hover:bg-felt-green/90 transition-colors"
      data-testid="poker-lobby-card"
    >
      <div className="flex items-center gap-2">
        <span className="font-display text-2xl tracking-wider">{t("TEXAS HOLD'EM")}</span>
        <span className="text-[10px] uppercase tracking-widest bg-gold-bright text-ink px-2 py-0.5 rounded-full border-2 border-ink">
          {t("Educational")}
        </span>
      </div>
      <p className="text-sm font-body text-cream/90 text-left">
        {t("Single-table tournament against 2–7 bot archetypes. Chipy coaches every decision.")}
      </p>
    </button>
  );
}
