/**
 * Lobby.tsx — the casino front door: one consistent game picker.
 *
 * Every game is a card that opens that game's own table browser
 * (Blackjack / Hold'em / Pai Gow) or setup (Solo Poker). Nothing game-specific
 * lives here — the lobby is purely "choose a game."
 */
import { useNavigate } from "react-router-dom";
import { t } from "../i18n";
import Chipy from "../components/Chipy";
import BlackjackLobbyCard from "../components/BlackjackLobbyCard";
import HoldemLobbyCard from "../components/HoldemLobbyCard";
import PokerLobbyCard from "../components/PokerLobbyCard";
import PaiGowLobbyCard from "../components/PaiGowLobbyCard";
import { StaggerList, StaggerItem } from "../motion/presence/StaggerList";
import BalanceHeader from "../components/BalanceHeader";

export default function Lobby() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "#1A0A00" }}>
      {/* Header */}
      <header
        className="flex flex-wrap items-center justify-between gap-y-2 px-4 py-4 border-b-[3px] border-ink"
        style={{ backgroundColor: "#0D3B1F" }}
      >
        <div className="flex items-center gap-3">
          <h1 className="font-display text-cream text-4xl sm:text-5xl gold-drop leading-none">
            BetWise
          </h1>
          <span className="font-display text-gold-mid text-xl tracking-widest hidden sm:inline">
            CASINO
          </span>
        </div>
        <nav className="flex flex-wrap items-center justify-end gap-3">
          <BalanceHeader />
          <button
            onClick={() => void navigate("/profile")}
            className="font-ui text-cream text-sm uppercase tracking-wider hover:text-gold-bright"
          >
            {t("Profile")}
          </button>
          <button
            onClick={() => void navigate("/leaderboard")}
            className="font-ui text-cream text-sm uppercase tracking-wider hover:text-gold-bright"
          >
            {t("Leaderboard")}
          </button>
          <div className="ml-2 hidden sm:block">
            <Chipy size={80} expression="idle" animation="idle" pose="wave" />
          </div>
        </nav>
      </header>

      <main className="flex-1 px-4 py-8 max-w-2xl mx-auto w-full">
        <h2
          className="text-cream text-4xl sm:text-5xl gold-drop leading-tight"
          style={{ fontFamily: "'Luckiest Guy', Impact, sans-serif", letterSpacing: "0.04em" }}
        >
          {t("Choose a Game")}
        </h2>
        <span className="font-flavor text-cream/70 text-sm italic">
          {t("Four ways to play — pick your poison.")}
        </span>

        <StaggerList className="flex flex-col gap-3 mt-4">
          <StaggerItem><BlackjackLobbyCard /></StaggerItem>
          <StaggerItem><HoldemLobbyCard /></StaggerItem>
          <StaggerItem><PokerLobbyCard /></StaggerItem>
          <StaggerItem><PaiGowLobbyCard /></StaggerItem>
        </StaggerList>
      </main>
    </div>
  );
}
