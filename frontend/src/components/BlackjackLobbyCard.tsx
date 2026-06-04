/**
 * BlackjackLobbyCard.tsx — entry point on the main lobby for Blackjack.
 *
 * Mirrors the Hold'em / Poker game cards so all three games read as one
 * consistent picker. Clicking it creates a fresh blackjack table and drops
 * the player straight onto the felt (the create+auto-join handler lives in
 * Lobby, where the loading/error state is owned, and is passed in as `onPlay`).
 */
import { t } from "../i18n";

interface BlackjackLobbyCardProps {
  /** Create a table and auto-join it (owned by Lobby.handleCreateTable). */
  onPlay: () => void;
  /** True while a table is being created/joined — disables the card. */
  busy?: boolean;
}

export default function BlackjackLobbyCard({ onPlay, busy = false }: BlackjackLobbyCardProps) {
  return (
    <button
      type="button"
      onClick={onPlay}
      disabled={busy}
      className="w-full ink-outline-thick paper-grain rounded-md p-5 flex items-center gap-4 text-left
        hover:bg-gold-bright/20 transition-colors disabled:opacity-40"
      style={{ backgroundColor: "#7B241C", boxShadow: "5px 5px 0 0 #1A0A00" }}
      data-testid="blackjack-lobby-card"
      aria-busy={busy}
    >
      <span className="text-4xl" aria-hidden="true">♣️</span>
      <span className="flex flex-col">
        <span className="font-display text-cream text-2xl leading-tight">
          {busy ? t("Dealing…") : t("Blackjack")}
        </span>
        <span className="font-flavor text-cream/70 text-sm italic">
          {t("Beat the dealer to 21 — Chipy coaches every hand.")}
        </span>
      </span>
    </button>
  );
}
