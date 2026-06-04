/**
 * PaiGowTablePage.tsx — the live PG table page.
 *
 * Uses usePaiGowPoll for the 3s state polling. Renders:
 * - FortunePoolTicker (top)
 * - Seats row
 * - Dealer area (cards visible at dealer_turn / finished)
 * - HandSetter when it's the player's turn (action_status === 'dealt')
 * - Betting controls when no active hand
 * - ChipyPaiGowCoach side panel (streams pre/post advice)
 * - Result banner after the round is resolved
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  dealPaiGowHand,
  leavePaiGowTable,
  streamPaiGowPostAdvice,
  streamPaiGowPreAdvice,
} from "../api/client";
import { useSession } from "../auth/supabase";
import ChipyPaiGowCoach from "../components/ChipyPaiGowCoach";
import FortunePoolTicker from "../components/FortunePoolTicker";
import HandSetter from "../components/HandSetter";
import PaiGowCardComp from "../components/PaiGowCard";
import PaiGowResultView from "../components/PaiGowResultView";
import PaiGowSeat from "../components/PaiGowSeat";
import { usePaiGowPoll } from "../hooks/usePaiGowPoll";
import { usePaiGowStore } from "../store/paiGowStore";
import type { PaiGowCard } from "../types";
import { t } from "../i18n";
import { formatMoney } from "../utils/money";

export default function PaiGowTablePage() {
  const { id: tableId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { session } = useSession();
  const currentUserId = session?.user.id ?? "";

  const { error: pollError, refetch } = usePaiGowPoll(tableId ?? null, currentUserId);
  const {
    tableState,
    myHand,
    beginChipyStream,
    appendChipyChunk,
    endChipyStream,
    setPreOptimal,
    setPostEvaluation,
    clearTableState,
  } = usePaiGowStore();

  const [bet, setBet] = useState(1_000);
  const [fortuneBet, setFortuneBet] = useState(0);
  const [dealing, setDealing] = useState(false);
  const [dealError, setDealError] = useState<string | null>(null);
  const preStreamedForHand = useRef<string | null>(null);
  const postStreamedForHand = useRef<string | null>(null);

  // Pre-set Chipy: fire when the local player has a fresh dealt hand.
  useEffect(() => {
    if (myHand === null) return;
    if (myHand.action_status !== "dealt") return;
    if (preStreamedForHand.current === myHand.id) return;
    preStreamedForHand.current = myHand.id;
    beginChipyStream("pre", myHand.id);
    void streamPaiGowPreAdvice(
      myHand.id,
      (chunk) => appendChipyChunk(chunk),
      (summary) => {
        endChipyStream();
        setPreOptimal(summary);
      },
      () => endChipyStream(),
    );
  }, [myHand, beginChipyStream, appendChipyChunk, endChipyStream, setPreOptimal]);

  // Post-set Chipy: fire when the local player's hand is resolved (or set
  // with cards filled in — we use front_cards as the trigger).
  useEffect(() => {
    if (myHand === null) return;
    if (myHand.front_cards === null || myHand.back_cards === null) return;
    if (postStreamedForHand.current === myHand.id) return;
    postStreamedForHand.current = myHand.id;
    beginChipyStream("post", myHand.id);
    void streamPaiGowPostAdvice(
      myHand.id,
      {
        front: myHand.front_cards as PaiGowCard[],
        back: myHand.back_cards as PaiGowCard[],
      },
      (chunk) => appendChipyChunk(chunk),
      (summary) => {
        endChipyStream();
        setPostEvaluation(summary);
      },
      () => endChipyStream(),
    );
  }, [
    myHand,
    beginChipyStream,
    appendChipyChunk,
    endChipyStream,
    setPostEvaluation,
  ]);

  // Auto-leave on unmount.
  useEffect(() => {
    return () => {
      clearTableState();
      if (tableId) void leavePaiGowTable(tableId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleDeal = useCallback(async (): Promise<void> => {
    if (!tableId) return;
    setDealError(null);
    setDealing(true);
    const res = await dealPaiGowHand(tableId, {
      bet_cents: bet,
      fortune_bet_cents: fortuneBet,
    });
    setDealing(false);
    if (res.data === null) {
      setDealError(res.error);
      return;
    }
    await refetch();
  }, [tableId, bet, fortuneBet, refetch]);

  if (tableId === undefined) {
    return (
      <main className="min-h-screen bg-felt-green p-4 text-cream">
        {t("Invalid table id")}
      </main>
    );
  }

  if (tableState === null) {
    return (
      <main className="min-h-screen bg-felt-green p-4 text-cream font-ui">
        {pollError !== null ? `${t("Error")}: ${pollError}` : t("Loading…")}
      </main>
    );
  }

  const seats: Array<typeof tableState.seats[number] | null> = Array.from(
    { length: tableState.max_seats },
    (_, i) => tableState.seats.find((s) => s.seat_number === i + 1) ?? null,
  );

  const round = tableState.round;
  const showBettingControls =
    round === null ||
    round.status === "finished" ||
    (round.status === "betting" && myHand === null) ||
    (round.status === "playing" && myHand === null);
  const showHandSetter =
    myHand !== null && myHand.action_status === "dealt" && myHand.dealt_cards !== null;
  const showResult = myHand !== null && myHand.hand_result !== null;

  return (
    <main className="min-h-screen bg-felt-green p-3 sm:p-6 text-cream">
      <header className="flex items-center justify-between mb-4 max-w-5xl mx-auto">
        <button
          type="button"
          onClick={() => void navigate("/pai-gow/lobby")}
          className="px-3 py-2 rounded-md border-[3px] border-ink bg-cream text-ink
            font-ui uppercase text-xs"
        >
          {t("← Lobby")}
        </button>
        <FortunePoolTicker />
      </header>

      <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-4">
        <section>
          {/* Dealer area — hidden on `finished` because PaiGowResultView
              shows the dealer + player split side-by-side. */}
          {(round === null || round.status !== "finished") && (
            <div className="ink-outline-thick rounded-xl p-3 mb-4 bg-ink/70">
              <h2 className="font-display text-cream text-xl tracking-wider mb-2">
                {t("Dealer")}
              </h2>
              {round !== null && round.dealer_dealt_cards !== null ? (
                <div className="flex flex-wrap gap-2">
                  {round.dealer_dealt_cards.map((c, i) => (
                    <PaiGowCardComp key={`d${i}`} card={c} index={i} noAnimate />
                  ))}
                </div>
              ) : (
                <p className="font-flavor italic text-cream/70 text-sm">
                  {round === null
                    ? t("No round yet.")
                    : t("Dealer cards reveal at the end of the round.")}
                </p>
              )}
            </div>
          )}

          {/* Seats */}
          <div className="flex flex-wrap gap-2 justify-center mb-4">
            {seats.map((s, i) => (
              <PaiGowSeat
                key={i}
                seat={s}
                seatNumber={i + 1}
                isCurrentUser={s?.user_id === currentUserId}
              />
            ))}
          </div>

          {/* Player's hand area */}
          {showHandSetter && myHand !== null && (
            <HandSetter hand={myHand} onSubmitted={() => void refetch()} />
          )}

          {showResult && myHand !== null && round !== null && (
            <PaiGowResultView round={round} myHand={myHand} />
          )}

          {showBettingControls && (
            <div className="ink-outline-thick rounded-xl p-3 bg-cream text-ink mt-4">
              <h3 className="font-display text-xl tracking-wider mb-2">
                {t("Place your bet")}
              </h3>
              <div className="flex flex-wrap gap-3 items-end">
                <label className="font-ui text-xs uppercase tracking-widest">
                  {t("Ante")} ({formatMoney(tableState.min_bet_cents)}–{formatMoney(tableState.max_bet_cents)})
                  <input
                    type="number"
                    value={bet / 100}
                    onChange={(e) => setBet(Math.round(parseFloat(e.target.value) * 100) || 0)}
                    min={tableState.min_bet_cents / 100}
                    max={tableState.max_bet_cents / 100}
                    className="block px-2 py-1 border-[3px] border-ink rounded-md font-body w-24"
                  />
                </label>
                <label className="font-ui text-xs uppercase tracking-widest">
                  {t("Fortune")} ({formatMoney(tableState.min_fortune_bet_cents)}–{formatMoney(tableState.max_fortune_bet_cents)})
                  <input
                    type="number"
                    value={fortuneBet / 100}
                    onChange={(e) => setFortuneBet(Math.round(parseFloat(e.target.value) * 100) || 0)}
                    min={0}
                    max={tableState.max_fortune_bet_cents / 100}
                    className="block px-2 py-1 border-[3px] border-ink rounded-md font-body w-24"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => void handleDeal()}
                  disabled={dealing}
                  className="px-6 py-3 rounded-md border-[3px] border-ink bg-gold-bright
                    text-ink font-ui uppercase tracking-widest disabled:opacity-40 min-h-[44px]"
                >
                  {dealing ? t("Dealing…") : t("Deal")}
                </button>
              </div>
              {dealError !== null && (
                <p role="alert" className="text-red-700 font-ui text-sm mt-2">
                  {dealError}
                </p>
              )}
            </div>
          )}
        </section>

        <ChipyPaiGowCoach />
      </div>
    </main>
  );
}
