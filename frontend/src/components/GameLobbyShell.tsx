/**
 * GameLobbyShell.tsx — shared chrome for every per-game lobby/setup screen.
 *
 * One consistent look across Blackjack / Hold'em / Solo Poker / Pai Gow: dark
 * felt background, green title bar with the game name, and an "← All Games"
 * button back to the picker. Each game drops its own table list / setup form
 * in as children.
 */
import { type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { t } from "../i18n";

interface GameLobbyShellProps {
  title: string;
  subtitle?: string;
  /** Optional element rendered on the right of the title bar (e.g. a New Table button). */
  action?: ReactNode;
  children: ReactNode;
}

export default function GameLobbyShell({ title, subtitle, action, children }: GameLobbyShellProps) {
  const navigate = useNavigate();
  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "#1A0A00" }}>
      <header
        className="flex items-center justify-between gap-3 px-4 py-4 border-b-[3px] border-ink"
        style={{ backgroundColor: "#0D3B1F" }}
      >
        <div className="min-w-0">
          <h1 className="font-display text-cream text-3xl sm:text-4xl gold-drop leading-none truncate">
            {title}
          </h1>
          {subtitle && (
            <p className="font-flavor text-cream/70 text-sm italic mt-1">{subtitle}</p>
          )}
        </div>
        <button
          type="button"
          onClick={() => void navigate("/lobby")}
          className="shrink-0 font-ui text-cream text-sm uppercase tracking-wider hover:text-gold-bright"
        >
          {t("← All Games")}
        </button>
      </header>

      <main className="flex-1 px-4 py-8 max-w-2xl mx-auto w-full">
        {action && <div className="flex justify-end mb-4">{action}</div>}
        {children}
      </main>
    </div>
  );
}
