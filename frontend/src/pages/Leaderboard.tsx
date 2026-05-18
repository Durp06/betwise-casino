/**
 * Leaderboard.tsx — Cuphead pivot. "HIGH ROLLERS" board.
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

const MEDAL_COLOR: Record<number, string> = {
  1: "#F4D03F",   // gold
  2: "#BDC3C7",   // silver
  3: "#CD7F32",   // bronze
};

function Medal({ rank }: { rank: number }) {
  const color = MEDAL_COLOR[rank];
  if (!color) return null;
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx={12} cy={12} r={10} fill={color} stroke="#1A0A00" strokeWidth={2} />
      <text
        x={12} y={16} textAnchor="middle"
        fontFamily="Luckiest Guy, sans-serif" fontSize={11}
        fill="#1A0A00"
      >
        {rank}
      </text>
    </svg>
  );
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
      if (result.error) setError(result.error);
      else setRows(result.data);
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "#1A0A00" }}>
      <header
        className="flex items-center justify-between px-4 py-4 border-b-[3px] border-ink"
        style={{ backgroundColor: "#0D3B1F" }}
      >
        <h1 className="font-display text-cream text-2xl gold-drop">{t("Leaderboard")}</h1>
        <button
          onClick={() => void navigate("/lobby")}
          className="font-ui text-cream uppercase tracking-wider text-xs hover:text-gold-bright"
        >
          {t("← Lobby")}
        </button>
      </header>

      <main className="flex-1 px-4 py-8 max-w-2xl mx-auto w-full">
        {/* Title plate */}
        <div className="flex items-center justify-center gap-3 mb-6">
          <div className="flex-1 h-1 bg-gradient-to-r from-transparent to-gold-mid rounded-full" />
          <h2 className="font-display text-gold-bright text-4xl gold-drop">
            HIGH ROLLERS
          </h2>
          <div className="flex-1 h-1 bg-gradient-to-l from-transparent to-gold-mid rounded-full" />
        </div>

        {loading && (
          <div role="status" aria-busy="true" className="flex flex-col gap-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="ink-outline h-14 rounded-md animate-pulse"
                style={{ backgroundColor: "#F5F0E8", opacity: 0.5 }}
              />
            ))}
          </div>
        )}

        {!loading && error && (
          <p role="alert" className="font-flavor text-action-hit text-center py-8 italic">
            {error}
          </p>
        )}

        {!loading && !error && rows !== null && rows.length === 0 && (
          <p className="font-flavor text-cream/60 text-center py-8 italic">
            {t("No players yet.")}
          </p>
        )}

        {!loading && !error && rows !== null && rows.length > 0 && (
          <div className="flex flex-col gap-2">
            {/* Header */}
            <div className="grid grid-cols-[2.5rem_1fr_auto_auto_auto] gap-3 px-3
              font-ui text-cream/70 text-[10px] uppercase tracking-widest">
              <span>#</span>
              <span>{t("Player")}</span>
              <span className="text-right">{t("Chips")}</span>
              <span className="text-right hidden sm:block">{t("Acc")}</span>
              <span className="text-right hidden sm:block">{t("Streak")}</span>
            </div>

            {rows.map((row) => {
              const isMe = row.user_id === session?.user.id;
              const isTopThree = row.rank <= 3;
              return (
                <div
                  key={row.user_id}
                  className="ink-outline grid grid-cols-[2.5rem_1fr_auto_auto_auto]
                    gap-3 px-3 py-3 rounded-md items-center"
                  style={{
                    backgroundColor: isMe ? "#F4D03F" : "#F5F0E8",
                    borderLeft: isMe ? "8px solid #C0392B" : "3px solid #1A0A00",
                    boxShadow: "3px 3px 0 0 #1A0A00",
                  }}
                >
                  <span className="flex items-center">
                    {isTopThree ? <Medal rank={row.rank} /> : (
                      <span className="font-display text-ink text-xl">{row.rank}</span>
                    )}
                  </span>
                  <span className="font-ui text-ink truncate">
                    {row.username}
                    {isMe && (
                      <span className="ml-1 font-flavor text-xs text-ink/60">{t("(you)")}</span>
                    )}
                  </span>
                  <span className="text-right font-display text-action-stand">
                    {formatCents(row.chip_balance)}
                  </span>
                  <span className="text-right font-flavor text-ink text-xs hidden sm:block">
                    {row.total_hands > 0 ? `${Math.round(row.accuracy_pct)}%` : "—"}
                  </span>
                  <span className="text-right font-display text-action-hit hidden sm:block">
                    {row.best_streak > 0 ? `🔥 ${row.best_streak}` : "—"}
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
