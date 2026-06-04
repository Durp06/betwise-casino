/**
 * PokerReviewModal.tsx — shared compute-on-read review modal for poker.
 *
 * One modal serves both games (Hold'em "table_visit" + solo poker "tournament")
 * and both shapes:
 *   - Hand Review  (mode="hand")  → per-decision list: verdict chip, your
 *     action vs recommended, equity vs required, ev_loss, explanation, plus a
 *     worst-action callout.
 *   - Game Review  (mode="game")  → summary header (overall accuracy %, total
 *     EV lost) + scrollable per-hand list; clicking a hand drills into that
 *     hand's Hand Review (which fetches lazily).
 *
 * Reuses the blackjack ClassificationChip so verdict colors match across the
 * app. Every fetch handles BOTH loading and error (CLAUDE.md §15). User-facing
 * strings go through t(). No `any`.
 */
import { useState, useEffect, useCallback } from "react";
import type {
  PokerReview,
  PokerReviewAction,
  PokerGameReview,
  PokerReviewGame,
  PokerReviewVerdict,
  Classification,
  ApiResult,
} from "../types";
import {
  getHoldemHandReview,
  getHoldemTableReview,
  getPokerHandReview,
  getPokerTournamentReview,
} from "../api/client";
import { ClassificationChip } from "./SessionReviewModal";
import EvalBar from "./EvalBar";
import PlayingCard from "./PlayingCard";
import ModalShell from "../motion/presence/ModalShell";
import { t } from "../i18n";

// ─── Public prop API ──────────────────────────────────────────────────────────
//
// Discriminated on `mode`. Hand mode reviews ONE hand; game mode reviews a whole
// tournament/table visit and lets the user drill into any hand.

interface PokerReviewModalHandProps {
  mode: "hand";
  game: PokerReviewGame;
  /** The hand to review (a Hold'em hand id, or a solo poker hand id). */
  handId: string;
  onClose: () => void;
}

interface PokerReviewModalGameProps {
  mode: "game";
  game: PokerReviewGame;
  /** The scope id: a Hold'em table id (table_visit) or a poker tournament id. */
  gameId: string;
  onClose: () => void;
}

export type PokerReviewModalProps =
  | PokerReviewModalHandProps
  | PokerReviewModalGameProps;

// ─── Verdict → chip mapping ─────────────────────────────────────────────────
//
// PokerReviewVerdict adds "no_verdict" to the five graded verdicts. The shared
// ClassificationChip handles best/good/inaccuracy/mistake/blunder; "no_verdict"
// gets a neutral grey chip rendered locally.

const GRADED_VERDICTS: ReadonlySet<PokerReviewVerdict> = new Set([
  "best",
  "good",
  "inaccuracy",
  "mistake",
  "blunder",
]);

function VerdictChip({ verdict }: { verdict: PokerReviewVerdict }) {
  if (GRADED_VERDICTS.has(verdict)) {
    // Safe narrowing: the five graded verdicts are exactly the non-"sharp"
    // members of Classification.
    return <ClassificationChip cls={verdict as Classification} />;
  }
  return (
    <span className="inline-block px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wide bg-white/10 text-white/60">
      {t("no verdict")}
    </span>
  );
}

// ─── Hand Review body ───────────────────────────────────────────────────────

function HoleCards({ cards }: { cards: PokerReview["your_hole"] }) {
  if (cards.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] text-white/50 uppercase tracking-wide">{t("Your hole cards")}</span>
      <div className="flex gap-1">
        {cards.map((card, i) => (
          <PlayingCard key={i} card={card} size="sm" noAnimate />
        ))}
      </div>
    </div>
  );
}

function Board({ cards }: { cards: PokerReview["board"] }) {
  if (cards.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] text-white/50 uppercase tracking-wide">{t("Board")}</span>
      <div className="flex gap-1">
        {cards.map((card, i) => (
          <PlayingCard key={i} card={card} size="sm" noAnimate />
        ))}
      </div>
    </div>
  );
}

function fmtBb(n: number): string {
  return `${n.toFixed(2)} ${t("bb")}`;
}

function fmtPct(n: number | null): string | null {
  if (n == null) return null;
  return `${Math.round(n * 100)}%`;
}

function ActionRow({ action, isWorst }: { action: PokerReviewAction; isWorst: boolean }) {
  const equityPct = fmtPct(action.equity);
  const requiredPct = fmtPct(action.required_equity);
  // EvalBar reuse: show the equity-vs-required comparison as a two-row bar.
  const evalEvs: Record<string, number> | undefined =
    action.equity != null && action.required_equity != null
      ? { [t("equity")]: action.equity, [t("required")]: action.required_equity }
      : undefined;

  return (
    <li
      data-testid="poker-review-action"
      className={`flex flex-col gap-2 py-3 border-b border-white/10 last:border-none ${isWorst ? "bg-red-500/10 -mx-2 px-2 rounded" : ""}`}
    >
      <div className="flex items-center gap-2 flex-wrap">
        <VerdictChip verdict={action.verdict} />
        <span className="text-[10px] text-white/40 uppercase tracking-wide">{action.street}</span>
        <span className="text-xs text-white/60">
          {t("You:")}{" "}
          <span className="font-bold text-white capitalize">{action.action}</span>
          {action.recommended_action != null && (
            <>
              {" "}/ {t("Best:")}{" "}
              <span className="font-bold text-chip-gold capitalize">{action.recommended_action}</span>
            </>
          )}
        </span>
        {action.ev_loss_bb != null && action.ev_loss_bb > 0 && (
          <span className="text-xs text-red-300 ml-auto" data-testid="poker-review-evloss">
            -{fmtBb(action.ev_loss_bb)}
          </span>
        )}
      </div>

      {(equityPct != null || requiredPct != null) && (
        <p className="text-xs text-white/60">
          {equityPct != null && (
            <>
              {t("Equity:")} <span className="text-white tabular-nums">{equityPct}</span>
            </>
          )}
          {requiredPct != null && (
            <>
              {" · "}
              {t("Required:")} <span className="text-white tabular-nums">{requiredPct}</span>
            </>
          )}
        </p>
      )}

      {evalEvs && <EvalBar actionEvs={evalEvs} bestAction={t("equity")} />}

      {action.explanation && (
        <p className="text-white/60 text-xs italic bg-white/5 p-2 rounded-lg leading-relaxed">
          {action.explanation}
        </p>
      )}
    </li>
  );
}

function HandReviewBody({ review }: { review: PokerReview }) {
  const worstIndex = review.worst_action_index;
  const worstAction =
    worstIndex != null
      ? review.actions.find((a) => a.action_index === worstIndex) ?? null
      : null;

  return (
    <>
      {/* Summary */}
      <div className="flex items-center gap-4 flex-shrink-0 text-sm">
        <div className="flex flex-col items-center">
          <span className="text-2xl font-bold text-chip-gold">
            {Math.round(review.accuracy * 100)}%
          </span>
          <span className="text-white/50 text-xs uppercase tracking-wide">{t("Accuracy")}</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-xl font-bold text-red-300 tabular-nums">
            {review.ev_lost_bb.toFixed(2)}
          </span>
          <span className="text-white/50 text-xs uppercase tracking-wide">{t("EV Lost (bb)")}</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-xl font-bold text-white">{review.graded_count}</span>
          <span className="text-white/50 text-xs uppercase tracking-wide">{t("Graded")}</span>
        </div>
      </div>

      {/* Cards */}
      <div className="flex items-end gap-4 flex-shrink-0">
        <HoleCards cards={review.your_hole} />
        <Board cards={review.board} />
      </div>

      {/* Worst-action callout */}
      {worstAction && (
        <div className="flex-shrink-0 bg-red-500/10 border border-red-500/30 rounded-xl p-3 flex flex-col gap-1">
          <h3 className="text-xs font-bold text-red-300 uppercase tracking-wide">
            {t("Worst decision")}
          </h3>
          <span className="text-xs text-white/70">
            {worstAction.street} — {t("You:")}{" "}
            <span className="font-bold text-white capitalize">{worstAction.action}</span>
            {worstAction.recommended_action != null && (
              <>
                {" /"} {t("Best:")}{" "}
                <span className="font-bold text-chip-gold capitalize">{worstAction.recommended_action}</span>
              </>
            )}
          </span>
        </div>
      )}

      {/* Action list */}
      {review.actions.length === 0 ? (
        <p className="text-white/40 text-center py-4">
          {t("No graded decisions for this hand.")}
        </p>
      ) : (
        <ul className="overflow-y-auto max-h-[55vh] flex-1">
          {review.actions.map((action) => (
            <ActionRow
              key={action.action_index}
              action={action}
              isWorst={worstIndex != null && action.action_index === worstIndex}
            />
          ))}
        </ul>
      )}
    </>
  );
}

// ─── Game Review body ───────────────────────────────────────────────────────

function GameReviewBody({
  review,
  onPickHand,
}: {
  review: PokerGameReview;
  onPickHand: (handId: string) => void;
}) {
  return (
    <>
      {/* Summary */}
      <div className="flex items-center gap-4 flex-shrink-0 text-sm">
        <div className="flex flex-col items-center">
          <span className="text-2xl font-bold text-chip-gold">
            {Math.round(review.overall_accuracy * 100)}%
          </span>
          <span className="text-white/50 text-xs uppercase tracking-wide">{t("Overall accuracy")}</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-xl font-bold text-red-300 tabular-nums">
            {review.total_ev_lost_bb.toFixed(2)}
          </span>
          <span className="text-white/50 text-xs uppercase tracking-wide">{t("Total EV lost (bb)")}</span>
        </div>
        <div className="flex flex-col items-center">
          <span className="text-xl font-bold text-white">{review.graded_count}</span>
          <span className="text-white/50 text-xs uppercase tracking-wide">{t("Graded")}</span>
        </div>
      </div>

      {/* Per-hand list */}
      {review.hands.length === 0 ? (
        <p className="text-white/40 text-center py-4">
          {t("No hands to review yet.")}
        </p>
      ) : (
        <ul className="overflow-y-auto max-h-[60vh] flex-1 flex flex-col gap-1">
          {review.hands.map((h, i) => (
            <li key={h.hand_id}>
              <button
                type="button"
                data-testid="poker-review-hand-row"
                onClick={() => onPickHand(h.hand_id)}
                className="w-full flex items-center gap-3 py-2 px-2 rounded hover:bg-white/10 text-left"
              >
                <span className="text-white/50 text-xs w-12 tabular-nums">
                  {t("Hand")} {i + 1}
                </span>
                {h.worst_verdict && <VerdictChip verdict={h.worst_verdict} />}
                <span className="text-sm text-white tabular-nums">
                  {Math.round(h.accuracy * 100)}%
                </span>
                <span className="text-xs text-white/50">
                  {h.graded_count} {t("graded")}
                </span>
                {h.ev_lost_bb > 0 && (
                  <span className="text-xs text-red-300 ml-auto tabular-nums">
                    -{h.ev_lost_bb.toFixed(2)} {t("bb")}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

// ─── Container ──────────────────────────────────────────────────────────────

export default function PokerReviewModal(props: PokerReviewModalProps) {
  const { game, onClose } = props;

  // Game-review mode can drill into a hand: when set, we render a Hand Review
  // for `drillHandId` with a Back button. In hand mode, drillHandId stays null
  // and we render the single hand directly.
  const [drillHandId, setDrillHandId] = useState<string | null>(
    props.mode === "hand" ? props.handId : null,
  );

  // Game-review payload (only fetched in game mode).
  const [gameReview, setGameReview] = useState<PokerGameReview | null>(null);
  const [gameLoading, setGameLoading] = useState(props.mode === "game");
  const [gameError, setGameError] = useState<string | null>(null);

  // Hand-review payload (fetched for the active hand id).
  const [handReview, setHandReview] = useState<PokerReview | null>(null);
  const [handLoading, setHandLoading] = useState(props.mode === "hand");
  const [handError, setHandError] = useState<string | null>(null);

  const fetchHandReview = useCallback(
    (handId: string): Promise<ApiResult<PokerReview>> =>
      game === "holdem" ? getHoldemHandReview(handId) : getPokerHandReview(handId),
    [game],
  );

  // Game-review fetch (game mode only). Depend on stable primitives so internal
  // state changes (e.g. drilling into a hand) don't refire this fetch.
  const gameScopeId = props.mode === "game" ? props.gameId : null;
  useEffect(() => {
    if (gameScopeId == null) return;
    let cancelled = false;
    setGameLoading(true);
    setGameError(null);
    const fetcher =
      game === "holdem"
        ? getHoldemTableReview(gameScopeId)
        : getPokerTournamentReview(gameScopeId);
    void fetcher.then((result) => {
      if (cancelled) return;
      setGameLoading(false);
      if (result.error) setGameError(result.error);
      else setGameReview(result.data);
    });
    return () => {
      cancelled = true;
    };
  }, [gameScopeId, game]);

  // Hand-review fetch (whenever drillHandId is set).
  useEffect(() => {
    if (!drillHandId) {
      setHandReview(null);
      return;
    }
    let cancelled = false;
    setHandLoading(true);
    setHandError(null);
    setHandReview(null);
    void fetchHandReview(drillHandId).then((result) => {
      if (cancelled) return;
      setHandLoading(false);
      if (result.error) setHandError(result.error);
      else setHandReview(result.data);
    });
    return () => {
      cancelled = true;
    };
  }, [drillHandId, fetchHandReview]);

  const inDrill = drillHandId != null;
  const showBack = props.mode === "game" && inDrill;
  const title = inDrill ? t("Hand Review") : t("Game Review");

  return (
    <ModalShell
      onClose={onClose}
      ariaLabel={title}
      panelClassName="bg-chipy-dark rounded-2xl w-full max-w-lg p-6 flex flex-col gap-4 max-h-[90vh]"
    >
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          {showBack && (
            <button
              type="button"
              onClick={() => setDrillHandId(null)}
              className="text-white/60 hover:text-white text-sm font-ui"
              data-testid="poker-review-back"
            >
              ← {t("Back")}
            </button>
          )}
          <h2 className="font-display text-chip-gold font-bold text-xl">{title}</h2>
        </div>
        <button
          onClick={onClose}
          className="text-white/60 hover:text-white text-2xl leading-none"
          aria-label={t("Close review")}
        >
          ×
        </button>
      </div>

      {/* Hand Review surface (hand mode, or a drilled hand in game mode) */}
      {inDrill ? (
        <>
          {handLoading && (
            <div role="status" aria-busy="true" className="text-center py-8">
              <span className="text-chip-gold animate-pulse">{t("Loading review...")}</span>
            </div>
          )}
          {!handLoading && handError && (
            <div role="alert" className="text-red-400 text-center py-4">
              {handError}
            </div>
          )}
          {!handLoading && !handError && handReview && (
            <HandReviewBody review={handReview} />
          )}
        </>
      ) : (
        // Game Review surface (game mode, no drill).
        <>
          {gameLoading && (
            <div role="status" aria-busy="true" className="text-center py-8">
              <span className="text-chip-gold animate-pulse">{t("Loading review...")}</span>
            </div>
          )}
          {!gameLoading && gameError && (
            <div role="alert" className="text-red-400 text-center py-4">
              {gameError}
            </div>
          )}
          {!gameLoading && !gameError && gameReview && (
            <GameReviewBody review={gameReview} onPickHand={setDrillHandId} />
          )}
        </>
      )}
    </ModalShell>
  );
}
