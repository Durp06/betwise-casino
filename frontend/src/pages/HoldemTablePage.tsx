/**
 * HoldemTablePage.tsx — the live multiplayer Hold'em felt.
 *
 * Mirrors the blackjack Table.tsx conventions: polls via useHoldemPoll, reads
 * state from the store, leaves on unmount (so an absent player doesn't stall
 * the table), gates the action bar on "it's your turn", and shows explicit
 * loading + error states. Reuses Board / PotDisplay; renders one HoldemSeat per
 * physical chair around the felt.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useSession } from "../auth/supabase";
import { useGameStore } from "../store/gameStore";
import { useHoldemPoll } from "../hooks/useHoldemPoll";
import {
  dealHoldemHand,
  getHoldemTableState,
  leaveHoldemTable,
} from "../api/client";
import Board from "../components/Board";
import PotDisplay from "../components/PotDisplay";
import HoldemSeat from "../components/HoldemSeat";
import HoldemActionBar from "../components/HoldemActionBar";
import WaitingForPlayers from "../components/WaitingForPlayers";
import ChatPanel from "../components/ChatPanel";
import HoldemRulesModal from "../components/HoldemRulesModal";
import { DeckProvider } from "../motion/DeckProvider";
import DeckStack from "../components/DeckStack";
import ChipFly from "../components/ChipFly";
import { useTableActionFeed } from "../motion/useTableActionFeed";
import { AnimatePresence } from "framer-motion";
import { t } from "../i18n";

export default function HoldemTablePage() {
  const { id: tableId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { session } = useSession();
  const currentUserId = session?.user.id ?? null;

  const holdemTableState = useGameStore((s) => s.holdemTableState);
  const setHoldemTableState = useGameStore((s) => s.setHoldemTableState);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [showRules, setShowRules] = useState(false);

  useHoldemPoll(tableId ?? "", setPollError);

  // Multiplayer presence: per-seat badges + chips-to-pot flies from the action log.
  const currentHand = holdemTableState?.current_hand ?? null;
  const actionEvents = useTableActionFeed(currentHand);
  const [lastActionBySeat, setLastActionBySeat] = useState<
    Record<number, { action: string; amount: number; key: number }>
  >({});
  const [flies, setFlies] = useState<{ id: number; seat: number; amount: number }[]>([]);
  useEffect(() => {
    if (actionEvents.length === 0) return;
    const timers: number[] = [];
    for (const ev of actionEvents) {
      setLastActionBySeat((prev) => ({
        ...prev,
        [ev.seatNumber]: { action: ev.action, amount: ev.amount, key: ev.actionIndex },
      }));
      if (["bet", "raise", "call", "all_in"].includes(ev.action)) {
        setFlies((prev) => [...prev, { id: ev.actionIndex, seat: ev.seatNumber, amount: ev.amount }]);
      }
      const seatNum = ev.seatNumber;
      const idx = ev.actionIndex;
      const tid = window.setTimeout(() => {
        setLastActionBySeat((prev) => {
          if (prev[seatNum]?.key !== idx) return prev;
          const next = { ...prev };
          delete next[seatNum];
          return next;
        });
      }, 1800);
      timers.push(tid);
    }
    return () => timers.forEach((id) => window.clearTimeout(id));
  }, [actionEvents]);

  const refresh = useCallback(async () => {
    if (!tableId) return;
    const result = await getHoldemTableState(tableId);
    if (result.error) setError(result.error);
    else {
      setHoldemTableState(result.data);
      setError(null);
    }
  }, [tableId, setHoldemTableState]);

  // Leave (cash out / fold) on unmount so an absent player can't stall the table.
  // Guard against React StrictMode's dev-only mount→cleanup→mount double-invoke:
  // the cleanup schedules the leave on a macrotask tagged with the table id, and
  // a synchronous remount for the SAME table cancels it — so a just-seated player
  // isn't cashed out on the synthetic unmount. On a genuine unmount nothing
  // remounts to cancel, so the leave fires; and switching to a different table id
  // leaves the old one correctly (the pending leave is not cancelled).
  const pendingLeaveRef = useRef<string | null>(null);
  useEffect(() => {
    if (pendingLeaveRef.current === tableId) pendingLeaveRef.current = null;
    const leavingTableId = tableId;
    return () => {
      setHoldemTableState(null);
      if (!leavingTableId) return;
      pendingLeaveRef.current = leavingTableId;
      setTimeout(() => {
        if (pendingLeaveRef.current === leavingTableId) {
          pendingLeaveRef.current = null;
          void leaveHoldemTable(leavingTableId);
        }
      }, 0);
    };
  }, [tableId, setHoldemTableState]);

  async function handleDeal(): Promise<void> {
    if (!tableId) return;
    setBusy(true);
    setError(null);
    const result = await dealHoldemHand(tableId);
    setBusy(false);
    if (result.error) setError(result.error);
    else setHoldemTableState(result.data);
  }

  if (!tableId) {
    return (
      <div role="alert" className="min-h-screen bg-felt-green flex items-center justify-center text-cream">
        {t("No table selected")}
      </div>
    );
  }

  if (!holdemTableState) {
    if (pollError) {
      return (
        <div className="min-h-screen bg-felt-green flex items-center justify-center">
          <div role="alert" className="flex flex-col items-center gap-4 p-6 bg-ink/80 rounded-xl text-cream">
            <p className="font-flavor text-action-hit">{t("Connection lost — could not load table")}</p>
            <p className="text-sm text-cream/70">{pollError}</p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => { setPollError(null); void refresh(); }}
                className="px-4 py-2 border-2 border-cream text-cream rounded font-ui uppercase tracking-wider hover:bg-cream hover:text-ink"
              >
                {t("Retry")}
              </button>
              <a
                href="/holdem"
                className="px-4 py-2 border-2 border-cream text-cream rounded font-ui uppercase tracking-wider hover:bg-cream hover:text-ink"
              >
                {t("Back to lobby")}
              </a>
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="min-h-screen bg-felt-green flex items-center justify-center">
        <span role="status" aria-busy="true" className="text-cream animate-pulse">
          {t("Pulling up a chair…")}
        </span>
      </div>
    );
  }

  const { table, seats, current_hand, your_seat_number } = holdemTableState;
  const hand = current_hand;
  const seated = seats.some((s) => s.user_id === currentUserId);
  const isHandActive = hand !== null && hand.status === "active";
  const canDeal = seated && !isHandActive && seats.length >= 2;

  const yourHandSeat =
    hand && your_seat_number !== null
      ? hand.seats.find((hs) => hs.seat_number === your_seat_number) ?? null
      : null;
  const isMyTurn =
    isHandActive && yourHandSeat !== null && hand.current_to_act_seat === your_seat_number;

  const chairs = Array.from({ length: table.max_seats }, (_, i) => i);

  return (
    <DeckProvider>
    <div className="min-h-screen bg-felt-green flex flex-col">
      <header className="flex items-center justify-between px-4 py-3 border-b-[3px] border-ink bg-ink/80">
        <h1 className="font-display text-cream text-2xl">
          {table.name} · {t("Hold'em")}
        </h1>
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => setShowRules(true)}
            className="font-ui text-cream text-sm uppercase tracking-wider hover:text-gold-bright"
          >
            {t("How to Play")}
          </button>
          <button
            onClick={() => void navigate("/holdem")}
            className="font-ui text-cream text-sm uppercase tracking-wider hover:text-gold-bright"
          >
            {t("Leave Table")}
          </button>
        </div>
      </header>

      {error && (
        <p role="alert" className="font-flavor text-action-hit text-sm px-4 py-2 italic">
          {error}
        </p>
      )}

      <main className="flex-1 flex flex-col items-center gap-6 p-6 relative">
        <DeckStack className="absolute top-4 right-4 scale-[0.7] origin-top-right opacity-90 pointer-events-none" />
        {/* Board + pot */}
        <div className="flex flex-col items-center gap-3 mt-4">
          <PotDisplay
            potTotal={hand?.pot_total ?? 0}
            sidePots={hand?.side_pots ?? []}
          />
          <Board cards={hand?.board ?? []} />
          {hand && (
            <span className="font-ui text-cream/70 text-xs uppercase tracking-wider" data-testid="holdem-street">
              {hand.street}
            </span>
          )}
        </div>

        {/* Seats */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 w-full max-w-3xl">
          {chairs.map((chair) => {
            const occupant = seats.find((s) => s.seat_number === chair) ?? null;
            const handSeat = hand?.seats.find((hs) => hs.table_seat_number === chair) ?? null;
            const isButton = hand !== null && handSeat !== null && hand.button_seat === handSeat.seat_number;
            const isCurrentToAct =
              isHandActive && handSeat !== null && hand.current_to_act_seat === handSeat.seat_number;
            const isYou =
              (occupant?.user_id ?? handSeat?.user_id ?? null) === currentUserId && currentUserId !== null;
            return (
              <HoldemSeat
                key={chair}
                chairNumber={chair}
                occupant={occupant}
                handSeat={handSeat}
                isCurrentToAct={isCurrentToAct}
                isButton={isButton}
                isYou={isYou}
                lastAction={handSeat ? lastActionBySeat[handSeat.seat_number]?.action ?? null : null}
                lastActionAmount={handSeat ? lastActionBySeat[handSeat.seat_number]?.amount ?? 0 : 0}
              />
            );
          })}
        </div>

        {/* Chips arcing to the pot when a seat bets/raises/calls */}
        {flies.map((f) => (
          <ChipFly
            key={f.id}
            seatNumber={f.seat}
            amount={f.amount}
            onDone={() => setFlies((prev) => prev.filter((x) => x.id !== f.id))}
          />
        ))}

        {/* Controls */}
        <div className="w-full max-w-md flex flex-col items-center gap-3">
          {canDeal && (
            <button
              onClick={() => void handleDeal()}
              disabled={busy}
              className="ink-outline-thick ink-shadow font-display tracking-wider px-6 py-3 rounded-md text-cream text-lg uppercase bg-action-stand disabled:opacity-40 min-h-[52px]"
              data-testid="holdem-deal-button"
            >
              {busy ? t("Dealing…") : t("Deal Hand")}
            </button>
          )}

          {/* Seated, but not enough players to deal yet — keep the felt alive
              instead of showing a dead table (Hold'em needs ≥2 humans). */}
          {seated && !isHandActive && seats.length < 2 && (
            <WaitingForPlayers seated={seats.length} needed={2} />
          )}

          {!seated && (
            <p className="font-flavor text-cream/70 text-sm italic" data-testid="holdem-not-seated">
              {t("You're watching. Take a seat from the lobby to play.")}
            </p>
          )}

          {isHandActive && !isMyTurn && seated && (
            <p className="font-flavor text-cream/70 text-sm italic" data-testid="holdem-waiting">
              {t("Waiting for other players…")}
            </p>
          )}

          {isMyTurn && yourHandSeat && (
            <HoldemActionBar
              tableId={tableId}
              hand={hand}
              yourSeat={yourHandSeat}
              onActed={() => void refresh()}
            />
          )}
        </div>

        {/* In-game chat — unobtrusive panel below the controls. */}
        <ChatPanel tableKind="holdem" tableId={tableId} />
      </main>

      <AnimatePresence>
        {showRules && <HoldemRulesModal key="rules" onClose={() => setShowRules(false)} />}
      </AnimatePresence>
    </div>
    </DeckProvider>
  );
}
