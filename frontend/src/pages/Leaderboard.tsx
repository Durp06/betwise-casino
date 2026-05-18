/**
 * Leaderboard.tsx — top 20 players by chip balance, current user highlighted.
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../auth/supabase";
import { getLeaderboard } from "../api/client";
import type { LeaderboardRow } from "../types";
import { t } from "../i18n";

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export default function Leaderboard() {
  const navigate = useNavigate();
  const { session } = useSession();
  const [rows, setRows] = useState<LeaderboardRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLeaderboard().then((result) => {
      if (cancelled) return;
      setLoading(false);
      if (result.error) {
        setError(result.error);
      } else {
        setRows(result.data);
      }
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="min-h-screen bg-felt-green flex flex-col">
      <header className="bg-chipy-dark px-4 py-3 flex items-center justify-between">
        <h1 className="font-display text-chip-gold font-bold text-xl">{t("Leaderboard")}</h1>
        <button onClick={() => void navigate("/lobby")} className="text-white/60 hover:text-white text-sm">
          {t("← Lobby")}
        </button>
      </header>

      <main className="flex-1 px-4 py-6 max-w-2xl mx-auto w-full">
        {loading && (
          <div role="status" aria-busy="true" className="flex flex-col gap-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-14 bg-white/10 rounded-xl animate-pulse" />
            ))}
          </div>
        )}

        {!loading && error && (
          <p role="alert" className="text-card-red text-center py-8">{error}</p>
        )}

        {!loading && !error && rows !== null && rows.length === 0 && (
          <p className="text-white/40 text-center py-8">{t("No players yet.")}</p>
        )}

        {!loading && !error && rows !== null && rows.length > 0 && (
          <div className="flex flex-col gap-1">
            {/* Header row */}
            <div className="grid grid-cols-[2rem_1fr_auto_auto_auto] gap-2 px-3 py-1
              text-xs text-white/40 uppercase tracking-wide">
              <span>#</span>
              <span>{t("Player")}</span>
              <span className="text-right">{t("Chips")}</span>
              <span className="text-right hidden sm:block">{t("Acc%")}</span>
              <span className="text-right hidden sm:block">{t("Streak")}</span>
            </div>

            {rows.map((row) => {
              const isMe = row.user_id === session?.user.id;
              return (
                <div
                  key={row.user_id}
                  className={`grid grid-cols-[2rem_1fr_auto_auto_auto] gap-2 px-3 py-3
                    rounded-xl items-center
                    ${isMe
                      ? "bg-chip-gold/20 border border-chip-gold"
                      : "bg-chipy-dark"
                    }`}
                >
                  <span className={`font-bold text-sm ${isMe ? "text-chip-gold" : "text-white/60"}`}>
                    {row.rank}
                  </span>
                  <span className={`font-medium truncate text-sm ${isMe ? "text-chip-gold" : "text-white"}`}>
                    {row.username}
                    {isMe && <span className="ml-1 text-xs opacity-60">{t("(you)")}</span>}
                  </span>
                  <span className="text-right text-sm font-bold text-green-400">
                    {formatCents(row.chip_balance)}
                  </span>
                  <span className="text-right text-xs text-white/60 hidden sm:block">
                    {row.total_hands > 0 ? `${Math.round(row.accuracy_pct)}%` : "—"}
                  </span>
                  <span className="text-right text-xs text-chip-gold hidden sm:block">
                    {row.best_streak > 0 ? `🔥${row.best_streak}` : "—"}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
