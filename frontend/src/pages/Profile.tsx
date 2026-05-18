/**
 * Profile.tsx — chip balance, total hands, accuracy, streak, weakness list,
 * hand history (last 20).
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../auth/supabase";
import { getMe, getWeakness, getUserHands, resetChips } from "../api/client";
import type { UserStats, WeakSpot, Hand } from "../types";
import { t } from "../i18n";

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export default function Profile() {
  const navigate = useNavigate();
  const { session } = useSession();
  const [stats, setStats] = useState<UserStats | null>(null);
  const [weakness, setWeakness] = useState<WeakSpot[] | null>(null);
  const [hands, setHands] = useState<Hand[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resetMsg, setResetMsg] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;

    async function load(): Promise<void> {
      const [statsRes, weakRes, handsRes] = await Promise.all([
        getMe(),
        getWeakness(),
        getUserHands(session!.user.id),
      ]);
      if (cancelled) return;
      setLoading(false);
      if (statsRes.error) { setError(statsRes.error); return; }
      setStats(statsRes.data);
      setWeakness(weakRes.error ? [] : weakRes.data);
      setHands(handsRes.error ? [] : handsRes.data);
    }

    void load();
    return () => { cancelled = true; };
  }, [session]);

  async function handleReset(): Promise<void> {
    setResetting(true);
    setResetMsg(null);
    const result = await resetChips();
    setResetting(false);
    if (result.error) {
      setResetMsg(result.error);
    } else {
      setStats(result.data);
      setResetMsg(t("Chips reset to $1,000.00!"));
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-felt-green flex items-center justify-center">
        <span role="status" aria-busy="true" className="text-white animate-pulse">
          {t("Loading...")}
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-felt-green flex flex-col items-center justify-center gap-4">
        <p role="alert" className="text-card-red">{error}</p>
        <button onClick={() => void navigate("/lobby")} className="text-chip-gold underline">
          {t("Back to Lobby")}
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-felt-green flex flex-col">
      <header className="bg-chipy-dark px-4 py-3 flex items-center justify-between">
        <h1 className="font-display text-chip-gold font-bold text-xl">{t("Profile")}</h1>
        <button onClick={() => void navigate("/lobby")} className="text-white/60 hover:text-white text-sm">
          {t("← Lobby")}
        </button>
      </header>

      <main className="flex-1 px-4 py-6 max-w-xl mx-auto w-full flex flex-col gap-5">
        {stats && (
          <>
            {/* Stats card */}
            <div className="bg-chipy-dark rounded-xl p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-white font-bold text-lg">{stats.username}</span>
                <span className="text-chip-gold font-bold">{formatCents(stats.chip_balance)}</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <span className="text-white/60">{t("Total hands:")}</span>
                  <span className="text-white ml-1 font-medium">{stats.total_hands}</span>
                </div>
                <div>
                  <span className="text-white/60">{t("Accuracy:")}</span>
                  <span className="text-white ml-1 font-medium">
                    {stats.total_hands > 0 ? `${Math.round(stats.accuracy * 100)}%` : "—"}
                  </span>
                </div>
                <div>
                  <span className="text-white/60">{t("Current streak:")}</span>
                  <span className="text-chip-gold ml-1 font-bold">{stats.current_streak}</span>
                </div>
                <div>
                  <span className="text-white/60">{t("Best streak:")}</span>
                  <span className="text-chip-gold ml-1 font-bold">{stats.best_streak}</span>
                </div>
              </div>
              <button
                onClick={() => void handleReset()}
                disabled={resetting || stats.chip_balance >= 1000}
                className="mt-1 text-xs text-white/40 hover:text-white/70 underline disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {resetting ? t("Resetting...") : t("Reset chips (when balance < $10)")}
              </button>
              {resetMsg && (
                <p className="text-sm text-green-400">{resetMsg}</p>
              )}
            </div>

            {/* Weakness detector */}
            {weakness !== null && weakness.length > 0 && (
              <div className="bg-chipy-dark rounded-xl p-4 flex flex-col gap-3">
                <h2 className="text-white font-bold">{t("Weak Spots")}</h2>
                <div className="flex flex-col gap-2">
                  {weakness.map((spot, i) => (
                    <div key={i} className="flex flex-col gap-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-white/70">
                          {spot.hand_category} {t("vs")} {t("dealer")} {spot.dealer_upcard_category}
                        </span>
                        <span className="text-card-red font-bold">
                          {Math.round(spot.accuracy * 100)}%
                        </span>
                      </div>
                      <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-card-red rounded-full"
                          style={{ width: `${spot.accuracy * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-white/40">
                        {spot.correct}/{spot.samples} {t("correct")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Hand history */}
            {hands !== null && (
              <div className="bg-chipy-dark rounded-xl p-4 flex flex-col gap-3">
                <h2 className="text-white font-bold">{t("Recent Hands")}</h2>
                {hands.length === 0 ? (
                  <p className="text-white/40 text-sm">{t("No hands played yet.")}</p>
                ) : (
                  <div className="flex flex-col gap-2">
                    {hands.map((hand) => (
                      <div key={hand.id} className="flex items-center justify-between text-sm">
                        <span className="text-white/60 capitalize">{hand.status}</span>
                        {hand.outcome && (
                          <span className={`font-bold capitalize ${
                            hand.outcome === "win" || hand.outcome === "blackjack"
                              ? "text-green-400"
                              : hand.outcome === "push"
                              ? "text-chip-gold"
                              : "text-card-red"
                          }`}>
                            {hand.outcome}
                          </span>
                        )}
                        <span className="text-white/40">{formatCents(hand.bet)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
