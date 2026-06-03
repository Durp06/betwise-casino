/**
 * HandHistory.tsx — Browsable hand-history page at /history.
 *
 * Fetches GET /api/users/me to get the current user's ID, then fetches
 * GET /api/users/:id/hands to load the hand list. Clicking a hand opens
 * the SessionReviewModal for that hand's session.
 *
 * AC-F-HIST1/2.
 */
import { useState, useEffect } from "react";
import { getMe, getUserHands } from "../api/client";
import type { Hand, UserStats } from "../types";
import SessionReviewModal from "../components/SessionReviewModal";
import { t } from "../i18n";
import { formatMoney } from "../utils/money";

export default function HandHistory() {
  const [me, setMe] = useState<UserStats | null>(null);
  const [hands, setHands] = useState<Hand[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewState, setReviewState] = useState<{
    sessionId: string;
    handId: string;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    async function load(): Promise<void> {
      const meRes = await getMe();
      if (cancelled) return;

      if (meRes.error !== null) {
        setLoading(false);
        setError(meRes.error);
        return;
      }

      const meData = meRes.data;
      setMe(meData);

      const handsRes = await getUserHands(meData.id);
      if (cancelled) return;

      setLoading(false);
      if (handsRes.error) {
        setError(handsRes.error);
        return;
      }
      setHands(handsRes.data);
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  // ─── Loading ───────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ backgroundColor: "#1A0A00" }}
      >
        <span role="status" aria-busy="true" className="font-flavor text-cream animate-pulse">
          {t("Loading...")}
        </span>
      </div>
    );
  }

  // ─── Error ─────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div
        className="min-h-screen flex flex-col items-center justify-center gap-4 px-6"
        style={{ backgroundColor: "#1A0A00" }}
      >
        <p role="alert" className="font-flavor text-action-hit italic text-center">
          {error}
        </p>
      </div>
    );
  }

  // ─── Empty state ───────────────────────────────────────────────────────────
  const isEmpty = hands !== null && hands.length === 0;

  // ─── Main render ───────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen flex flex-col" style={{ backgroundColor: "#1A0A00" }}>
      <header
        className="flex items-center justify-between px-4 py-4 border-b-[3px] border-ink"
        style={{ backgroundColor: "#0D3B1F" }}
      >
        <h1 className="font-display text-cream text-2xl gold-drop">
          {t("Hand History")}
        </h1>
        {me && (
          <span className="font-ui text-cream/60 text-xs uppercase tracking-wider">
            {me.username}
          </span>
        )}
      </header>

      <main className="flex-1 px-4 py-8 max-w-xl mx-auto w-full flex flex-col gap-4">
        {isEmpty ? (
          <p className="font-flavor text-cream/60 italic text-center py-8">
            {t("No hands played yet.")}
          </p>
        ) : (
          <div
            className="ink-outline-thick paper-grain rounded-md overflow-hidden"
            style={{ backgroundColor: "#F5F0E8", boxShadow: "5px 5px 0 0 #1A0A00" }}
          >
            {(hands ?? []).map((hand) => {
              const outcomeColor =
                hand.outcome === "win" || hand.outcome === "blackjack"
                  ? "text-action-stand"
                  : hand.outcome === "push"
                  ? "text-gold-dark"
                  : "text-action-hit";

              return (
                <button
                  key={hand.id}
                  data-testid="history-row"
                  onClick={() =>
                    setReviewState({ sessionId: hand.session_id, handId: hand.id })
                  }
                  className="w-full grid grid-cols-3 items-center text-sm py-3 px-4
                    border-b border-ink/15 last:border-0 hover:bg-gold-bright/10
                    transition-colors text-left"
                >
                  <span className="font-flavor text-ink/70 capitalize">
                    {hand.status}
                  </span>
                  <span
                    className={`font-ui uppercase tracking-wider text-center ${outcomeColor}`}
                  >
                    {hand.outcome ?? "—"}
                  </span>
                  <span className="font-ui text-ink/80 text-right">
                    {formatMoney(hand.bet)}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </main>

      {reviewState && (
        <SessionReviewModal
          sessionId={reviewState.sessionId}
          handId={reviewState.handId}
          onClose={() => setReviewState(null)}
        />
      )}
    </div>
  );
}
