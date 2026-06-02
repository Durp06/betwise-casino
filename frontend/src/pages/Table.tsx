/**
 * Table.tsx — main game screen, Cuphead pivot.
 *
 * Radial felt gradient background, cream sub-panels with ink outlines,
 * Chipy panel slides in from below when it's the player's turn.
 */
import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useGameStore } from "../store/gameStore";
import { useTablePoll } from "../hooks/useTablePoll";
import { useSession } from "../auth/supabase";
import { leaveTable, streamPreAdvice } from "../api/client";
import type { Action } from "../types";
import CardHand from "../components/CardHand";
import TableSeats from "../components/TableSeats";
import BettingControls from "../components/BettingControls";
import ActionBar from "../components/ActionBar";
import ChipyCoach from "../components/ChipyCoach";
import ReplayModal from "../components/ReplayModal";
import SessionReviewModal from "../components/SessionReviewModal";
import ChatPanel from "../components/ChatPanel";
import Chipy from "../components/Chipy";
import type { ChipyExpression, ChipyAnimation, ChipyPose } from "../components/Chipy";
import { t } from "../i18n";

// Maps a hand outcome (or status fallback) to Chipy's reaction state.
// Backend doesn't always set hand.outcome — a bust during the player's turn
// only flips hand.status to "bust". Treat the status as a secondary signal.
function chipyForOutcome(
  outcome: string | null | undefined,
  status: string | null | undefined,
): {
  expression: ChipyExpression;
  animation: ChipyAnimation;
  pose: ChipyPose;
  title: string;
} {
  const signal = outcome ?? status ?? null;
  switch (signal) {
    case "blackjack":
      return { expression: "happy", animation: "spin", pose: "thumbsup", title: "BLACKJACK!" };
    case "win":
      return { expression: "happy", animation: "bounce", pose: "thumbsup", title: "YOU WIN!" };
    case "push":
      return { expression: "idle", animation: "idle", pose: "rest", title: "PUSH" };
    case "loss":
      return { expression: "surprised", animation: "shake", pose: "point", title: "DEALER WINS" };
    case "bust":
      return { expression: "surprised", animation: "shake", pose: "rest", title: "BUST!" };
    case "finished":
      return { expression: "idle", animation: "idle", pose: "rest", title: "ROUND OVER" };
    default:
      return { expression: "idle", animation: "idle", pose: "rest", title: "" };
  }
}

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

  const {
    tableState,
    myHand,
    beginChipyStream,
    appendChipyChunk,
    endChipyStream,
    resetChipy,
    lastFinishedHandId,
    coachMode,
    setChipyDrillPrompt,
  } = useGameStore();

  const [replayHandId, setReplayHandId] = useState<string | null>(null);
  const [leaveLoading, setLeaveLoading] = useState(false);
  const [reviewIsLeaveFlow, setReviewIsLeaveFlow] = useState(false);
  const [reviewState, setReviewState] = useState<{
    sessionId: string;
    handId: string;
  } | null>(null);

  useTablePoll(tableId ?? "", currentUserId);

  // Proactive Chipy. In "quick" mode we fire the pre-stream so Chipy chimes
  // in with the recommendation before the player acts. In "drill" mode we
  // hold the recommendation back and surface a static quiz prompt instead;
  // the post-play stream still fires from ActionBar so Chipy reveals the
  // answer + dealer-bust % after the player commits.
  const lastPreHandRef = useRef<string | null>(null);
  useEffect(() => {
    if (!myHand) {
      lastPreHandRef.current = null;
      setChipyDrillPrompt(null);
      return;
    }
    const sessionPlaying = tableState?.session?.status === "playing";
    const handActive = myHand.status === "active";
    if (
      sessionPlaying &&
      handActive &&
      lastPreHandRef.current !== myHand.id
    ) {
      lastPreHandRef.current = myHand.id;
      const handId = myHand.id;
      if (coachMode === "quick") {
        setChipyDrillPrompt(null);
        beginChipyStream("pre", handId);
        void streamPreAdvice(
          handId,
          (chunk) => appendChipyChunk(chunk),
          () => endChipyStream(),
          () => endChipyStream(),
        );
      } else {
        // Drill mode: no proactive narration. Show the quiz line until the
        // player commits an action; ActionBar's streamAdvice will replace
        // it with the post-play reveal.
        setChipyDrillPrompt(
          t("Your call. Hit, stand, or double? What's the dealer most likely sitting on?"),
        );
      }
    }
  }, [
    myHand,
    tableState?.session?.status,
    coachMode,
    beginChipyStream,
    appendChipyChunk,
    endChipyStream,
    setChipyDrillPrompt,
  ]);

  // Wipe Chipy when leaving the table — keeps stale narration from flashing
  // when the user re-enters another table.
  useEffect(() => {
    return () => {
      resetChipy();
    };
  }, [resetChipy]);

  // Auto-leave when the user navigates away from the table page — covers
  // clicking the Lobby/Profile/Leaderboard buttons, the browser Back button,
  // and most refresh paths. Without this the user accumulated a stale seat
  // at every table they ever visited (caught when a smoke test found one
  // user seated at 7 different tables simultaneously). Fire-and-forget so
  // it doesn't block navigation.
  //
  // Tab close / hard refresh aren't reliably covered by useEffect cleanup
  // because the browser may cut the fetch off; for those cases the next
  // sign-in could clean up stale seats server-side, but that's a follow-up.
  useEffect(() => {
    if (!tableId) return;
    return () => {
      void leaveTable(tableId).catch(() => {
        /* fire-and-forget; user is already navigating away */
      });
    };
  }, [tableId]);

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

  async function handleLeave(): Promise<void> {
    // Defer navigation until after the review modal closes — otherwise
    // /lobby unmounts Table and the modal disappears with it. The review
    // is only meaningful for a hand that's actually FINISHED; leaving
    // mid-active-round shouldn't force the player through a partial review.
    if (!tableId) return;
    const handIsTerminal = myHand && myHand.status !== "active";
    if (handIsTerminal && tableState?.session) {
      setReviewIsLeaveFlow(true);
      setReviewState({ sessionId: tableState.session.id, handId: myHand.id });
      return;
    }
    setLeaveLoading(true);
    void navigate("/lobby");
  }

  function handleReviewClose(): void {
    setReviewState(null);
    if (reviewIsLeaveFlow) {
      setReviewIsLeaveFlow(false);
      setLeaveLoading(true);
      void navigate("/lobby");
    }
  }

  if (!tableId) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#1A0A00" }}>
        <p role="alert" className="font-flavor text-action-hit italic">{t("Invalid table ID")}</p>
      </div>
    );
  }

  if (!tableState) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: "#1A0A00" }}>
        <span role="status" aria-busy="true" className="font-flavor text-cream/70 animate-pulse">
          {t("Pulling up a chair...")}
        </span>
      </div>
    );
  }

  const dealerCards = tableState.session?.dealer_cards ?? [];

  // Treat "no session yet" or "previous session finished" both as "ready to deal."
  const canStartNewRound =
    (!tableState.session || sessionStatus === "finished") &&
    tableState.seats.some((s) => s.user_id === currentUserId);

  // A hand is "finished" if the backend assigned an outcome OR the status
  // moved to a terminal value (bust during play, blackjack, or explicit finished).
  const isHandFinished =
    myHand !== null &&
    (Boolean(myHand.outcome) ||
      myHand.status === "finished" ||
      myHand.status === "bust" ||
      myHand.status === "blackjack");
  const chipyMood = chipyForOutcome(myHand?.outcome, myHand?.status);

  return (
    <div className="table-surface min-h-screen flex flex-col">
      {/* Header */}
      <header
        className="flex items-center justify-between px-4 py-3 border-b-[3px] border-ink relative z-10"
        style={{ backgroundColor: "#0D3B1F" }}
      >
        <h1 className="font-display text-cream text-2xl gold-drop truncate">
          {tableState.name}
        </h1>
        <div className="flex gap-3 font-ui uppercase tracking-wider text-xs text-cream">
          <button
            onClick={() => void navigate("/lobby")}
            className="hover:text-gold-bright"
          >
            {t("Lobby")}
          </button>
          <button
            onClick={() => void handleLeave()}
            disabled={leaveLoading}
            className="text-action-hit hover:text-red-300 disabled:opacity-40"
          >
            {leaveLoading ? t("…") : t("Leave")}
          </button>
        </div>
      </header>

      <main className="flex-1 px-4 py-6 max-w-5xl mx-auto w-full relative z-10 flex flex-col lg:flex-row gap-5 items-start">
        <div className="flex-1 flex flex-col gap-5 w-full max-w-2xl mx-auto lg:mx-0">
        {/* Seats */}
        <TableSeats
          seats={tableState.seats}
          hands={tableState.hands}
          currentUserId={currentUserId}
        />

        {/* Felt table inset — dealer at top, then every seated player's hand */}
        {tableState.session && (
          <div
            className="ink-outline rounded-2xl p-5 flex flex-col gap-5"
            style={{
              backgroundColor: "#145A32",
              boxShadow: "4px 4px 0 0 #1A0A00, inset 0 0 60px rgba(0,0,0,0.45)",
            }}
          >
            <CardHand
              cards={dealerCards}
              handValue={handValueDisplay(dealerCards) ?? undefined}
              label="Dealer"
            />

            <div className="h-1 bg-ink rounded-full" />

            {/* Every player's hand — ordered by seat number (backend now sorts).
                Active player's panel gets an amber glow to telegraph whose
                turn it is. This is the multiplayer-feel pass. */}
            {tableState.hands.length === 0 && (
              <p className="font-flavor text-cream/60 italic text-sm text-center">
                {t("Waiting for the deal...")}
              </p>
            )}
            {tableState.hands.map((hand) => {
              const seat = tableState.seats.find((s) => s.user_id === hand.user_id);
              const isMine = hand.user_id === currentUserId;
              const isActive = hand.status === "active"
                && tableState.session?.status === "playing";
              const username = seat?.username ?? t("Player");

              return (
                <div
                  key={hand.id}
                  className={`rounded-xl p-3 transition-all duration-200
                    ${isActive ? "ring-4 ring-gold-bright" : ""}`}
                  style={{
                    backgroundColor: isMine ? "rgba(244, 208, 63, 0.08)" : "rgba(0,0,0,0.18)",
                    opacity: !isActive && !isMine && tableState.session?.status === "playing" ? 0.7 : 1,
                  }}
                >
                  {/* Player header row: name, bet, status badge */}
                  <div className="flex items-baseline justify-between mb-2 px-1 gap-2 flex-wrap">
                    <div className="flex items-baseline gap-2">
                      <span className="font-display text-cream text-lg uppercase tracking-wide">
                        {isMine ? t("YOU") : username}
                      </span>
                      {isActive && (
                        <span className="font-ui text-gold-bright text-[10px] uppercase tracking-widest animate-pulse">
                          ← {t("their turn")}
                        </span>
                      )}
                    </div>
                    <div className="flex items-baseline gap-2 text-xs">
                      <span className="font-flavor text-cream/70 uppercase tracking-wider">
                        {t("Bet")}
                      </span>
                      <span className="font-display text-gold-bright">
                        ${(hand.bet / 100).toFixed(2)}
                      </span>
                    </div>
                  </div>
                  <CardHand
                    cards={hand.cards}
                    handValue={handValueDisplay(hand.cards) ?? undefined}
                  />
                </div>
              );
            })}
          </div>
        )}

        {/* Outcome banner — Chipy reacts to the result, big readable announcement.
            Gated on lastFinishedHandId so stale hands from a prior session
            (visible to the user via tableState on first poll after joining)
            don't fire the banner. ActionBar sets it when a play ends the
            hand; BettingControls clears it on the next deal. */}
        {isHandFinished
          && myHand?.id === lastFinishedHandId
          && chipyMood.title && (
          <div
            className="ink-outline rounded-2xl flex items-center gap-4 px-5 py-4 paper-grain"
            style={{
              backgroundColor: "#F5F0E8",
              boxShadow: "5px 5px 0 0 #1A0A00",
            }}
          >
            <Chipy
              size={88}
              expression={chipyMood.expression}
              animation={chipyMood.animation}
              pose={chipyMood.pose}
            />
            <div className="flex-1">
              <h2 className="font-display text-action-hit text-3xl gold-drop leading-none">
                {chipyMood.title}
              </h2>
              {myHand?.payout !== undefined && myHand.payout !== null && myHand.payout > 0 && (
                <p className="font-ui text-action-stand text-base mt-1">
                  +${(myHand.payout / 100).toFixed(2)}
                </p>
              )}
              {chipyMood.title && (
                <p className="font-flavor text-ink/70 text-xs italic mt-0.5">
                  {chipyMood.expression === "happy"
                    ? "Now we're talkin', partner."
                    : chipyMood.expression === "surprised"
                    ? "Shake it off, you'll get the next one."
                    : "Even money — house just kept its powder dry."}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Betting controls — show when no session OR previous session finished */}
        {canStartNewRound && (
          <div id="post-hand-bet" className="flex flex-col items-center gap-2">
            {isHandFinished && (
              <p className="font-ui text-cream text-xl uppercase tracking-widest">
                {t("Place your next bet")}
              </p>
            )}
            <BettingControls
              tableId={tableId}
              minBet={500}
              maxBet={50000}
              chipBalance={
                tableState.seats.find((s) => s.user_id === currentUserId)?.chip_balance ?? 100000
              }
            />
          </div>
        )}

        {/* Action bar */}
        {sessionStatus === "playing" && isMyTurn && (
          <ActionBar
            tableId={tableId}
            legalActions={legalActions}
            isMyTurn={isMyTurn}
            handId={myHand?.id ?? null}
          />
        )}

        {/* Post-hand menu — appears after the hand finishes and the user can
            either deal again, replay the just-played hand, review the whole
            session, or leave. Replaces the two stray underlined links. */}
        {isHandFinished && tableState.session && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 w-full">
            <button
              onClick={() => {
                document
                  .getElementById("post-hand-bet")
                  ?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
              className="ink-outline ink-shadow py-3 rounded-md font-ui text-ink uppercase
                tracking-wider text-xs sm:text-sm bg-gold-bright min-h-[48px]"
            >
              {t("Play another hand")}
            </button>
            <button
              onClick={() => setReplayHandId(myHand!.id)}
              className="ink-outline ink-shadow py-3 rounded-md font-ui text-cream uppercase
                tracking-wider text-xs sm:text-sm bg-action-stand min-h-[48px]"
            >
              {t("Review last hand")}
            </button>
            <button
              onClick={() =>
                setReviewState({
                  sessionId: tableState.session!.id,
                  handId: myHand!.id,
                })
              }
              className="ink-outline ink-shadow py-3 rounded-md font-ui text-cream uppercase
                tracking-wider text-xs sm:text-sm bg-action-double min-h-[48px]"
            >
              {t("Review session")}
            </button>
            <button
              onClick={() => void handleLeave()}
              disabled={leaveLoading}
              className="ink-outline ink-shadow py-3 rounded-md font-ui text-cream uppercase
                tracking-wider text-xs sm:text-sm bg-action-hit min-h-[48px]
                disabled:opacity-40"
            >
              {leaveLoading ? t("…") : t("Leave table")}
            </button>
          </div>
        )}
        </div>

        {/* Always-on Chipy side rail + in-game chat. Pinned to the top on
            desktop so they don't shift as the felt grows; full-width above the
            felt on mobile (lg breakpoint flips the flex direction). */}
        <div className="flex flex-col gap-4 w-full lg:w-auto">
          <ChipyCoach />
          <ChatPanel tableKind="blackjack" tableId={tableId} />
        </div>
      </main>

      {replayHandId && (
        <ReplayModal handId={replayHandId} onClose={() => setReplayHandId(null)} />
      )}
      {reviewState && (
        <SessionReviewModal
          sessionId={reviewState.sessionId}
          handId={reviewState.handId}
          onClose={handleReviewClose}
        />
      )}
    </div>
  );
}
