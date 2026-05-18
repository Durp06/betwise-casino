/**
 * Table.tsx — main game screen. Uses useTablePoll for real-time-ish state.
 * Optimistic Hit: immediately appends null card placeholder.
 *
 * Saloon styling: a green felt "table surface" wraps the dealer + my hand,
 * walnut frame for everything else, brass divider between sections.
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
      <div className="min-h-screen flex items-center justify-center">
        <p role="alert" className="text-saloon-blood italic">{t("Invalid table ID")}</p>
      </div>
    );
  }

  if (!tableState) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <span role="status" aria-busy="true" className="text-saloon-parchment/70 animate-pulse">
          {t("Pulling up a chair...")}
        </span>
      </div>
    );
  }

  const dealerCards = tableState.session?.dealer_cards ?? [];

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header — walnut bar with brass-line edge */}
      <header className="saloon-panel px-4 py-3 flex items-center justify-between
        border-b border-saloon-brass/40">
        <h1
          className="text-saloon-amber font-bold text-lg tracking-wide truncate"
          style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}
        >
          {tableState.name}
        </h1>
        <div className="flex gap-3 text-xs uppercase tracking-wider">
          <button
            onClick={() => void navigate("/lobby")}
            className="text-saloon-ash hover:text-saloon-parchment transition-colors"
          >
            {t("Lobby")}
          </button>
          <button
            onClick={() => void handleLeave()}
            disabled={leaveLoading}
            className="text-saloon-blood hover:text-red-400 transition-colors disabled:opacity-40"
          >
            {leaveLoading ? t("...") : t("Leave")}
          </button>
        </div>
      </header>

      <main className="flex-1 flex flex-col gap-4 px-4 py-5 max-w-2xl mx-auto w-full">
        {/* Seats */}
        <TableSeats
          seats={tableState.seats}
          hands={tableState.hands}
          currentUserId={currentUserId}
        />

        {/* Felt table surface — wraps dealer + your hand */}
        {tableState.session && (
          <div className="saloon-felt rounded-2xl p-4 sm:p-6 flex flex-col gap-5
            ring-1 ring-saloon-brass/40">
            <div>
              <p className="text-saloon-amber/70 text-[10px] uppercase tracking-[0.3em] mb-2 text-center">
                {t("Dealer")}
              </p>
              <CardHand
                cards={dealerCards}
                handValue={handValueDisplay(dealerCards) ?? undefined}
              />
            </div>

            {/* Hairline brass divider across the felt */}
            <div className="h-px bg-saloon-brass/40" />

            {myHand && (
              <div className={`${actionError ? "ring-2 ring-saloon-blood rounded-md animate-shake" : ""}`}>
                <p className="text-saloon-amber/70 text-[10px] uppercase tracking-[0.3em] mb-2 text-center">
                  {t("Your hand")}
                </p>
                <CardHand
                  cards={myHand.cards}
                  handValue={handValueDisplay(myHand.cards) ?? undefined}
                />
                {myHand.outcome && (
                  <p
                    className="text-saloon-amber font-bold mt-3 capitalize text-center text-lg"
                    style={{ fontFamily: "'DM Serif Display', Georgia, serif" }}
                  >
                    {myHand.outcome}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {actionError && (
          <p role="alert" className="text-saloon-blood text-sm text-center italic">{actionError}</p>
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
            className="btn-leather w-full py-3 rounded-md font-bold uppercase tracking-widest
              min-h-[44px]"
          >
            {t("Deal Cards")}
          </button>
        )}

        {/* Action bar during play */}
        {sessionStatus === "playing" && isMyTurn && !chipyOpen && (
          <div className="flex flex-col gap-2">
            <button
              onClick={() => void handleOptimisticHit()}
              className="w-full py-3 rounded-md font-bold uppercase tracking-widest text-saloon-parchment
                bg-saloon-leather hover:bg-saloon-blood active:scale-[0.98] transition-all
                ring-1 ring-saloon-brass/40 min-h-[44px]"
            >
              {t("Hit (no coach)")}
            </button>
            <ActionBar
              tableId={tableId}
              legalActions={legalActions}
              isMyTurn={isMyTurn}
            />
          </div>
        )}

        {/* Chipy panel */}
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
            className="text-saloon-amber text-xs uppercase tracking-widest underline text-center"
          >
            {t("Review the hand")}
          </button>
        )}
      </main>

      {replayHandId && (
        <ReplayModal handId={replayHandId} onClose={() => setReplayHandId(null)} />
      )}
    </div>
  );
}
