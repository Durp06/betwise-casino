/**
 * Table.tsx — main game screen. Uses useTablePoll for real-time-ish state.
 * Optimistic Hit: immediately appends null card placeholder.
 */
import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useGameStore } from "../store/gameStore";
import { useTablePoll } from "../hooks/useTablePoll";
import { useSession } from "../auth/supabase";
import { dealHand, takeAction, leaveTable } from "../api/client";
import type { Action } from "../types";
import CardHand from "../components/CardHand";
import TableSeats from "../components/TableSeats";
import BettingControls from "../components/BettingControls";
import ActionBar from "../components/ActionBar";
import ChipyPanel from "../components/ChipyPanel";
import ReplayModal from "../components/ReplayModal";
import { t } from "../i18n";

// Naive hand value calculator for display (mirrors backend logic)
function handValueDisplay(cards: (({ suit: string; value: string }) | null)[]): number | null {
  const realCards = cards.filter((c): c is { suit: string; value: string } => c !== null);
  if (realCards.length === 0) return null;
  const VALUES: Record<string, number> = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11,
  };
  let total = 0;
  let aces = 0;
  for (const card of realCards) {
    total += VALUES[card.value] ?? 0;
    if (card.value === "A") aces++;
  }
  while (total > 21 && aces > 0) {
    total -= 10;
    aces--;
  }
  return total;
}

export default function Table() {
  const { id: tableId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { session } = useSession();
  const currentUserId = session?.user.id ?? null;

  const { tableState, myHand, chipyOpen, closeChipy, optimisticHit, rollbackOptimistic } =
    useGameStore();

  const [replayHandId, setReplayHandId] = useState<string | null>(null);
  const [leaveLoading, setLeaveLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useTablePoll(tableId ?? "", currentUserId);

  const sessionStatus = tableState?.session?.status;
  const myHandStatus = myHand?.status;
  const isMyTurn =
    sessionStatus === "playing" &&
    myHandStatus === "active";

  const legalActions: Action[] = ["hit", "stand"];
  if (myHand && myHand.cards.filter((c) => c !== null).length === 2) {
    legalActions.push("double");
    const realCards = myHand.cards.filter((c): c is NonNullable<typeof c> => c !== null);
    if (realCards.length === 2 && realCards[0].value === realCards[1].value) {
      legalActions.push("split");
    }
  }

  async function handleOptimisticHit(): Promise<void> {
    if (!tableId) return;
    const actionId = `opt-${Date.now()}`;
    optimisticHit(actionId);
    setActionError(null);

    const result = await takeAction(tableId, "hit");
    if (result.error) {
      rollbackOptimistic();
      setActionError(result.error);
    }
  }

  async function handleLeave(): Promise<void> {
    if (!tableId) return;
    setLeaveLoading(true);
    await leaveTable(tableId);
    void navigate("/lobby");
  }

  if (!tableId) {
    return (
      <div className="min-h-screen bg-felt-green flex items-center justify-center">
        <p role="alert" className="text-card-red">{t("Invalid table ID")}</p>
      </div>
    );
  }

  // Initial loading
  if (!tableState) {
    return (
      <div className="min-h-screen bg-felt-green flex items-center justify-center">
        <span role="status" aria-busy="true" className="text-white animate-pulse">
          {t("Loading table...")}
        </span>
      </div>
    );
  }

  const dealerCards = tableState.session?.dealer_cards ?? [];

  return (
    <div className="min-h-screen bg-felt-green flex flex-col">
      {/* Header */}
      <header className="bg-chipy-dark px-4 py-3 flex items-center justify-between">
        <h1 className="font-display text-chip-gold font-bold text-lg">{tableState.name}</h1>
        <div className="flex gap-2">
          <button
            onClick={() => void navigate("/lobby")}
            className="text-white/60 hover:text-white text-sm"
          >
            {t("Lobby")}
          </button>
          <button
            onClick={() => void handleLeave()}
            disabled={leaveLoading}
            className="text-card-red hover:text-red-400 text-sm disabled:opacity-40"
          >
            {leaveLoading ? t("Leaving...") : t("Leave")}
          </button>
        </div>
      </header>

      <main className="flex-1 flex flex-col gap-4 px-4 py-4 max-w-2xl mx-auto w-full">
        {/* Seats */}
        <TableSeats
          seats={tableState.seats}
          hands={tableState.hands}
          currentUserId={currentUserId}
        />

        {/* Dealer hand */}
        {tableState.session && (
          <div className="bg-black/20 rounded-xl p-3">
            <CardHand
              cards={dealerCards}
              handValue={handValueDisplay(dealerCards) ?? undefined}
              label="Dealer"
            />
          </div>
        )}

        {/* My hand */}
        {myHand && (
          <div className={`bg-black/20 rounded-xl p-3 ${actionError ? "ring-2 ring-card-red animate-shake" : ""}`}>
            <CardHand
              cards={myHand.cards}
              handValue={handValueDisplay(myHand.cards) ?? undefined}
              label="Your hand"
            />
            {myHand.outcome && (
              <p className="text-chip-gold font-bold mt-2 capitalize">{myHand.outcome}</p>
            )}
          </div>
        )}

        {actionError && (
          <p role="alert" className="text-card-red text-sm text-center">{actionError}</p>
        )}

        {/* Betting controls — show when session is in betting phase */}
        {sessionStatus === "betting" && (
          <BettingControls
            tableId={tableId}
            minBet={500}
            maxBet={50000}
            chipBalance={
              tableState.seats.find((s) => s.user_id === currentUserId)?.chip_balance ?? 100000
            }
          />
        )}

        {/* No session yet — deal button */}
        {!tableState.session && tableState.seats.some((s) => s.user_id === currentUserId) && (
          <button
            onClick={() => void dealHand(tableId, 500)}
            className="w-full py-3 bg-chip-gold text-chipy-dark font-bold rounded-lg
              hover:bg-yellow-400 active:scale-95 transition-all min-h-[44px]"
          >
            {t("Start Round")}
          </button>
        )}

        {/* Action bar during play */}
        {sessionStatus === "playing" && isMyTurn && !chipyOpen && (
          <div className="flex flex-col gap-2">
            {/* Quick optimistic hit */}
            <button
              onClick={() => void handleOptimisticHit()}
              className="w-full py-3 bg-green-600 text-white font-bold rounded-lg
                hover:bg-green-500 active:scale-95 transition-all min-h-[44px]"
            >
              {t("Hit")}
            </button>
            <ActionBar
              tableId={tableId}
              legalActions={legalActions}
              isMyTurn={isMyTurn}
            />
          </div>
        )}

        {/* Chipy panel — full-width bottom sheet on mobile */}
        {chipyOpen && myHand && tableState.session && (
          <div className="fixed inset-x-0 bottom-0 sm:relative sm:inset-auto z-40 sm:z-auto">
            <ChipyPanel
              handId={myHand.id}
              legalActions={legalActions}
              dealerUpcard={
                (tableState.session.dealer_cards[1] ?? tableState.session.dealer_cards[0]) as {
                  suit: string;
                  value: string;
                }
              }
              onConfirm={(action: Action) => {
                closeChipy();
                void takeAction(tableId, action);
              }}
            />
          </div>
        )}

        {/* Replay button when hand is done */}
        {myHand && (myHand.status === "finished" || myHand.outcome) && (
          <button
            onClick={() => setReplayHandId(myHand.id)}
            className="text-chip-gold text-sm underline text-center"
          >
            {t("Review hand")}
          </button>
        )}
      </main>

      {/* Replay modal */}
      {replayHandId && (
        <ReplayModal handId={replayHandId} onClose={() => setReplayHandId(null)} />
      )}
    </div>
  );
}
