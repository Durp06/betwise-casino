/**
 * PokerTablePage.tsx — the main table view for a Texas Hold'em SNG.
 *
 * Polls /state every 3s; renders all seats + board + pot + action bar
 * (when it's your turn) + Chipy coach. On first mount, fires deal so the
 * tournament is in a playable state.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate, Navigate } from "react-router-dom";
import { useGameStore } from "../store/gameStore";
import { usePokerPoll } from "../hooks/usePokerPoll";
import { dealPokerHand } from "../api/client";
import Board from "../components/Board";
import PotDisplay from "../components/PotDisplay";
import PokerSeat from "../components/PokerSeat";
import PokerActionBar from "../components/PokerActionBar";
import PokerChipyCoach from "../components/PokerChipyCoach";
import { t } from "../i18n";

export default function PokerTablePage() {
  const { id: tournamentId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const pokerTournamentState = useGameStore((s) => s.pokerTournamentState);
  const setPokerTournamentState = useGameStore((s) => s.setPokerTournamentState);
  const [dealing, setDealing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Always-on poll while mounted
  usePokerPoll(tournamentId ?? "");

  // On first mount, ensure a hand is dealt
  useEffect(() => {
    if (!tournamentId) return;
    let cancelled = false;
    async function ensureDealt(): Promise<void> {
      setDealing(true);
      const result = await dealPokerHand(tournamentId!);
      if (cancelled) return;
      setDealing(false);
      if (result.error || !result.data) {
        setError(result.error ?? "Failed to deal");
        return;
      }
      setPokerTournamentState(result.data);
    }
    void ensureDealt();
    return () => {
      cancelled = true;
    };
  }, [tournamentId, setPokerTournamentState]);

  if (!tournamentId) {
    return <Navigate to="/lobby" replace />;
  }

  if (error) {
    return (
      <main className="min-h-screen bg-felt-green text-cream p-6">
        <div
          role="alert"
          className="ink-outline-thick rounded-xl bg-red-100 text-red-900 p-4"
          data-testid="poker-table-error"
        >
          {error}
          <button
            type="button"
            onClick={() => void navigate("/lobby")}
            className="ml-4 px-3 py-1 border-2 border-ink bg-cream text-ink rounded"
          >
            {t("Back to lobby")}
          </button>
        </div>
      </main>
    );
  }

  if (!pokerTournamentState && dealing) {
    return (
      <main className="min-h-screen bg-felt-green text-cream p-6 flex items-center justify-center">
        <span role="status" aria-busy="true" className="animate-pulse">
          {t("Dealing first hand…")}
        </span>
      </main>
    );
  }

  if (!pokerTournamentState) {
    return (
      <main className="min-h-screen bg-felt-green text-cream p-6 flex items-center justify-center">
        <span role="status">{t("Loading…")}</span>
      </main>
    );
  }

  const { tournament, seats, current_hand: hand, your_seat_number } = pokerTournamentState;
  const yourSeatNumber = your_seat_number ?? 0;
  const yourHandSeat = hand?.seats.find((s) => s.seat_number === yourSeatNumber) ?? null;
  const isYourTurn = hand?.current_to_act_seat === yourSeatNumber;

  return (
    <main className="min-h-screen bg-felt-green text-cream p-4 flex flex-col gap-4 lg:flex-row" data-testid="poker-table-page">
      <section className="flex-1 flex flex-col gap-4">
        <header className="flex items-center justify-between">
          <h1 className="font-display text-2xl tracking-wider">
            {t("Hold'em Tournament")} #{tournament.current_hand_number}
          </h1>
          <button
            type="button"
            onClick={() => void navigate("/lobby")}
            className="text-xs font-ui underline"
            data-testid="poker-table-leave"
          >
            {t("Lobby")}
          </button>
        </header>

        {/* Felt — seats around the board */}
        <div className="bg-felt-green/80 ink-outline-thick rounded-3xl p-6 flex flex-col items-center gap-4">
          {hand && (
            <>
              <PotDisplay
                potTotal={hand.pot_total}
                sidePots={hand.side_pots as { amount: number; eligible: number[] }[]}
              />
              <Board cards={hand.board} />
            </>
          )}

          <div
            className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 w-full"
            data-testid="poker-seats-row"
          >
            {seats.map((seat) => {
              const handSeat = hand?.seats.find((s) => s.seat_number === seat.seat_number) ?? null;
              const isCurrent = hand?.current_to_act_seat === seat.seat_number;
              const isButton = hand?.button_seat === seat.seat_number;
              return (
                <PokerSeat
                  key={seat.seat_number}
                  seat={seat}
                  handSeat={handSeat}
                  isCurrentToAct={isCurrent}
                  isButton={isButton}
                  isYou={seat.seat_number === yourSeatNumber}
                />
              );
            })}
          </div>
        </div>

        {/* Action bar — only when it's your turn AND you have a hand */}
        {isYourTurn && hand && yourHandSeat && (
          <PokerActionBar
            tournamentId={tournamentId}
            hand={hand}
            yourSeat={yourHandSeat}
          />
        )}

        {!isYourTurn && hand && (
          <p className="text-cream/70 text-sm italic" data-testid="poker-waiting">
            {hand.current_to_act_seat !== null
              ? `${t("Waiting on seat")} ${hand.current_to_act_seat}…`
              : t("Hand complete. Next hand will be dealt shortly.")}
          </p>
        )}
      </section>

      <section className="lg:w-80">
        <PokerChipyCoach handId={hand?.id ?? null} />
      </section>
    </main>
  );
}

