/**
 * HoldemTablePage.tsx — the live multiplayer Hold'em felt.
 *
 * Mirrors the blackjack Table.tsx conventions: polls via useHoldemPoll, reads
 * state from the store, leaves on unmount (so an absent player doesn't stall
 * the table), gates the action bar on "it's your turn", and shows explicit
 * loading + error states. Reuses Board / PotDisplay; renders one HoldemSeat per
 * physical chair around the felt.
 */
import { useCallback, useEffect, useState } from "react";
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
import ChatPanel from "../components/ChatPanel";
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

  useHoldemPoll(tableId ?? "");

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
  useEffect(() => {
    return () => {
      if (tableId) void leaveHoldemTable(tableId);
      setHoldemTableState(null);
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
    <div className="min-h-screen bg-felt-green flex flex-col">
      <header className="flex items-center justify-between px-4 py-3 border-b-[3px] border-ink bg-ink/80">
        <h1 className="font-display text-cream text-2xl">
          {table.name} · {t("Hold'em")}
        </h1>
        <button
          onClick={() => void navigate("/holdem")}
          className="font-ui text-cream text-sm uppercase tracking-wider hover:text-gold-bright"
        >
          {t("Leave Table")}
        </button>
      </header>

      {error && (
        <p role="alert" className="font-flavor text-action-hit text-sm px-4 py-2 italic">
          {error}
        </p>
      )}

      <main className="flex-1 flex flex-col items-center gap-6 p-6">
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
              />
            );
          })}
        </div>

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
    </div>
  );
}
