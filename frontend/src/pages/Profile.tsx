/**
 * Profile.tsx — Cuphead-styled user profile.
 *
 * Shows: chip balance, total hands, accuracy, streak, weakness list,
 * and recent hand history. Reset-chips CTA available when balance < $10.
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../auth/supabase";
import { getMe, getWeakness, getUserHands, resetChips } from "../api/client";
import type { UserStats, WeakSpot, Hand } from "../types";
import { t } from "../i18n";
import Chipy from "../components/Chipy";

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export default function Profile() {
  const navigate = useNavigate();
  const { session, loading: sessionLoading } = useSession();
  const [stats, setStats] = useState<UserStats | null>(null);
  const [weakness, setWeakness] = useState<WeakSpot[] | null>(null);
  const [hands, setHands] = useState<Hand[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [resetMsg, setResetMsg] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    // Don't hang in "Loading" forever when session is null after auth resolves
    if (sessionLoading) return;
    if (!session) {
      setLoading(false);
      return;
    }
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
  }, [session, sessionLoading]);

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

  // ─── Auth gate ─────────────────────────────────────────────────────────
  if (!sessionLoading && !session) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 px-6"
        style={{ backgroundColor: "#1A0A00" }}>
        <Chipy size={120} expression="surprised" animation="idle" pose="rest" />
        <p className="font-ui text-cream text-xl text-center">
          {t("Sign in to see your profile.")}
        </p>
        <button
          onClick={() => void navigate("/login")}
          className="ink-outline-thick ink-shadow font-display tracking-wider
            px-5 py-3 rounded-md text-cream text-xl uppercase"
          style={{ backgroundColor: "#C0392B" }}
        >
          {t("Sign In")}
        </button>
      </div>
    );
  }

  // ─── Loading ───────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#1A0A00" }}>
        <span role="status" aria-busy="true" className="font-flavor text-cream animate-pulse">
          {t("Loading...")}
        </span>
      </div>
    );
  }

  // ─── Error ─────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 px-6"
        style={{ backgroundColor: "#1A0A00" }}>
        <Chipy size={120} expression="surprised" animation="shake" pose="rest" />
        <p role="alert" className="font-flavor text-action-hit italic text-center">{error}</p>
        <button
          onClick={() => void navigate("/lobby")}
          className="font-ui text-cream uppercase tracking-wider underline"
        >
          {t("Back to Lobby")}
        </button>
      </div>
    );
  }

  // ─── Main render ────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "#1A0A00" }}>
      <header
        className="flex items-center justify-between px-4 py-4 border-b-[3px] border-ink"
        style={{ backgroundColor: "#0D3B1F" }}
      >
        <h1 className="font-display text-cream text-2xl gold-drop">{t("Profile")}</h1>
        <button
          onClick={() => void navigate("/lobby")}
          className="font-ui text-cream uppercase tracking-wider text-xs hover:text-gold-bright"
        >
          {t("← Lobby")}
        </button>
      </header>

      <main className="flex-1 px-4 py-8 max-w-xl mx-auto w-full flex flex-col gap-5">
        {stats && (
          <>
            {/* Stats plaque */}
            <div
              className="ink-outline-thick paper-grain rounded-md p-5 flex flex-col gap-4"
              style={{ backgroundColor: "#F5F0E8", boxShadow: "5px 5px 0 0 #1A0A00" }}
            >
              <div className="flex items-center justify-between">
                <span className="font-display text-ink text-3xl">{stats.username}</span>
                <span className="font-display text-action-stand text-3xl gold-drop">
                  {formatCents(stats.chip_balance)}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <Stat label={t("Total hands")} value={String(stats.total_hands)} />
                <Stat
                  label={t("Accuracy")}
                  value={stats.total_hands > 0 ? `${Math.round(stats.accuracy * 100)}%` : "—"}
                />
                <Stat label={t("Current streak")} value={`🔥 ${stats.current_streak}`} amber />
                <Stat label={t("Best streak")} value={`🏆 ${stats.best_streak}`} amber />
              </div>

              <button
                onClick={() => void handleReset()}
                disabled={resetting || stats.chip_balance >= 1000}
                className="self-start font-flavor text-xs text-ink/60 underline
                  disabled:opacity-30 disabled:cursor-not-allowed hover:text-ink"
              >
                {resetting
                  ? t("Resetting…")
                  : stats.chip_balance >= 1000
                  ? t("Reset chips (only when balance < $10)")
                  : t("Reset chips to $1,000")}
              </button>
              {resetMsg && (
                <p className="font-flavor text-action-stand text-sm italic">{resetMsg}</p>
              )}
            </div>

            {/* Weakness detector */}
            {weakness !== null && weakness.length > 0 && (
              <div
                className="ink-outline-thick paper-grain rounded-md p-5 flex flex-col gap-3"
                style={{ backgroundColor: "#F5F0E8", boxShadow: "5px 5px 0 0 #1A0A00" }}
              >
                <h2 className="font-display text-ink text-2xl">{t("Weak Spots")}</h2>
                <p className="font-flavor text-ink/70 text-xs italic">
                  {t("Where your reads are off — work these first.")}
                </p>
                <div className="flex flex-col gap-3 mt-1">
                  {weakness.map((spot, i) => (
                    <div key={i} className="flex flex-col gap-1">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-ui text-ink">
                          {spot.hand_category} {t("vs")} {spot.dealer_upcard_category}
                        </span>
                        <span className="font-display text-action-hit">
                          {Math.round(spot.accuracy * 100)}%
                        </span>
                      </div>
                      <div className="ink-outline w-full h-2.5 bg-cream rounded-full overflow-hidden">
                        <div
                          className="h-full bg-action-hit"
                          style={{ width: `${Math.max(spot.accuracy * 100, 3)}%` }}
                        />
                      </div>
                      <span className="font-flavor text-ink/60 text-[10px]">
                        {spot.correct}/{spot.samples} {t("correct")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recent hands */}
            {hands !== null && (
              <div
                className="ink-outline-thick paper-grain rounded-md p-5 flex flex-col gap-3"
                style={{ backgroundColor: "#F5F0E8", boxShadow: "5px 5px 0 0 #1A0A00" }}
              >
                <h2 className="font-display text-ink text-2xl">{t("Recent Hands")}</h2>
                {hands.length === 0 ? (
                  <p className="font-flavor text-ink/60 italic text-sm">
                    {t("No hands played yet.")}
                  </p>
                ) : (
                  <div className="flex flex-col gap-1">
                    {hands.map((hand) => {
                      const outcomeColor =
                        hand.outcome === "win" || hand.outcome === "blackjack"
                          ? "text-action-stand"
                          : hand.outcome === "push"
                          ? "text-gold-dark"
                          : "text-action-hit";
                      return (
                        <div
                          key={hand.id}
                          className="grid grid-cols-3 items-center text-sm py-1 border-b border-ink/15 last:border-0"
                        >
                          <span className="font-flavor text-ink/70 capitalize">
                            {hand.status}
                          </span>
                          <span className={`font-ui uppercase tracking-wider text-center ${outcomeColor}`}>
                            {hand.outcome ?? "—"}
                          </span>
                          <span className="font-ui text-ink/80 text-right">
                            {formatCents(hand.bet)}
                          </span>
                        </div>
                      );
                    })}
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

interface StatProps {
  label: string;
  value: string;
  amber?: boolean;
}
function Stat({ label, value, amber }: StatProps) {
  return (
    <div className="flex flex-col">
      <span className="font-flavor text-ink/60 text-[10px] uppercase tracking-widest">
        {label}
      </span>
      <span
        className={`font-display text-2xl ${amber ? "text-gold-dark" : "text-ink"}`}
      >
        {value}
      </span>
    </div>
  );
}
