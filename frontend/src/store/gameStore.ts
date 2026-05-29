/**
 * store/gameStore.ts — Zustand store for BetWise Casino game state.
 *
 * Silver feature: optimistic Hit with rollback.
 * Gold feature: pendingActionId guard prevents polling from double-applying
 *               an optimistic update that's already been sent to the server.
 */
import { create } from "zustand";
import type { Card, Hand, TableState, PokerTournamentState } from "../types";

const COACH_MODE_STORAGE_KEY = "betwise.coachMode";
const POKER_COACH_MODE_STORAGE_KEY = "betwise.pokerCoachMode";

function loadCoachMode(): "quick" | "drill" {
  if (typeof window === "undefined") return "quick";
  try {
    const raw = window.localStorage.getItem(COACH_MODE_STORAGE_KEY);
    if (raw === "quick" || raw === "drill") return raw;
  } catch {
    // localStorage may throw in sandboxed iframes; fall through.
  }
  return "quick";
}

function loadPokerCoachMode(): "reads" | "odds" {
  if (typeof window === "undefined") return "odds";
  try {
    const raw = window.localStorage.getItem(POKER_COACH_MODE_STORAGE_KEY);
    if (raw === "reads" || raw === "odds") return raw;
  } catch {
    // ignore
  }
  return "odds";
}

// ─── State shape ──────────────────────────────────────────────────────────────

interface GameState {
  tableState: TableState | null;
  myHand: Hand | null;
  isMyTurn: boolean;
  chipyOpen: boolean;
  chipyMessage: string;
  chipyLoading: boolean;
  betAmount: number;
  /** Set to a client-generated UUID when an optimistic hit is in flight. */
  pendingActionId: string | null;
  /** Face-down card placeholders inserted by optimisticHit. */
  pendingOptimisticCards: Card[];

  // ─── ChipyCoach (always-on side panel) ──────────────────────────────────
  /** Accumulated narration text Chipy is currently streaming. */
  chipyText: string;
  /** True while an SSE stream is in flight. */
  chipyStreaming: boolean;
  /** Which phase the coach is in — drives the banner label + mascot mood. */
  chipyPhase: "idle" | "pre" | "post";
  /** ID of the hand the current narration is about (so stale pre-streams
   *  for a previous hand can be ignored once a new one starts). */
  chipyHandId: string | null;
  /** ID of the most recent hand the local player saw finish *during this
   *  visit*. Used to gate the celebratory "DEALER WINS / YOU WIN" banner
   *  so a stale finished hand from a prior session doesn't fire it on
   *  fresh join or page refresh. Set by ActionBar on terminal result,
   *  cleared by BettingControls on the next deal. */
  lastFinishedHandId: string | null;

  // ─── Drill Mode (active-retrieval coaching) ─────────────────────────────
  /** Coaching style. "quick" = current behavior (Chipy reveals before you act).
   *  "drill" = Chipy holds back the recommendation and quizzes you instead.
   *  Persisted in localStorage under "betwise.coachMode". */
  coachMode: "quick" | "drill";
  /** Static drill-mode question shown when no narration is streaming. Owned
   *  by Table.tsx's pre-stream effect; ChipyCoach reads it. Null in quick
   *  mode or after Chipy starts narrating. */
  chipyDrillPrompt: string | null;

  // ─── Texas Hold'em poker ──────────────────────────────────────────────────
  /** Last polled tournament state from /api/poker/tournaments/{id}/state. */
  pokerTournamentState: PokerTournamentState | null;
  /** UI-only coach mode for poker — persisted to localStorage. Default "odds"
   *  per the spec's open-question 3 (safer default for an educational tool). */
  pokerCoachMode: "reads" | "odds";
  /** Active Chipy text for poker (mirrors chipyText but for poker SSE). */
  pokerCoachText: string;
  /** True while a poker SSE is in flight. */
  pokerCoachStreaming: boolean;
  /** Last final SSE event from poker advice — drives the confidence badge. */
  pokerCoachConfidenceTier: "DETERMINISTIC" | "HEURISTIC" | null;
  pokerCoachRecommendedAction: string | null;
}

// ─── Actions shape ────────────────────────────────────────────────────────────

interface GameActions {
  setTableState: (state: TableState) => void;
  setMyHand: (hand: Hand | null) => void;
  openChipy: () => void;
  closeChipy: () => void;
  setChipyMessage: (message: string) => void;
  setChipyLoading: (loading: boolean) => void;
  placeBet: (amount: number) => void;
  /**
   * optimisticHit — immediately appends a null-card placeholder to myHand.cards
   * and records the pending action id so the reconciler can match it.
   */
  optimisticHit: (actionId: string) => void;
  /**
   * rollbackOptimistic — clears placeholders and pendingActionId.
   * Called by client.ts on error.
   */
  rollbackOptimistic: () => void;
  /**
   * reconcileFromPoll — pure reducer applied on every polling response.
   * Replaces placeholder cards with real cards from the server when the
   * pending action id is no longer in flight (i.e., the server has processed it).
   */
  reconcileFromPoll: (newState: TableState, currentUserId: string) => void;

  // ─── ChipyCoach actions ─────────────────────────────────────────────────
  /** Start a new Chipy narration. Clears prior text and flips streaming on. */
  beginChipyStream: (phase: "pre" | "post", handId: string) => void;
  /** Append one SSE text chunk to the current narration. */
  appendChipyChunk: (chunk: string) => void;
  /** Mark the SSE stream as done. */
  endChipyStream: () => void;
  /** Wipe Chipy back to idle (e.g. after a round ends). */
  resetChipy: () => void;
  /** Set or clear the "just finished this visit" hand id (banner gate). */
  setLastFinishedHandId: (handId: string | null) => void;
  /** Flip Quick/Drill and persist to localStorage. */
  setCoachMode: (mode: "quick" | "drill") => void;
  /** Set or clear the static drill prompt shown by ChipyCoach. */
  setChipyDrillPrompt: (prompt: string | null) => void;

  // ─── Texas Hold'em actions ────────────────────────────────────────────────
  setPokerTournamentState: (state: PokerTournamentState | null) => void;
  setPokerCoachMode: (mode: "reads" | "odds") => void;
  appendPokerCoachChunk: (text: string) => void;
  beginPokerCoachStream: () => void;
  endPokerCoachStream: (
    confidenceTier: "DETERMINISTIC" | "HEURISTIC" | null,
    recommendedAction: string | null,
  ) => void;
  resetPokerCoach: () => void;
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useGameStore = create<GameState & GameActions>((set, get) => ({
  tableState: null,
  myHand: null,
  isMyTurn: false,
  chipyOpen: false,
  chipyMessage: "",
  chipyLoading: false,
  betAmount: 500,
  pendingActionId: null,
  pendingOptimisticCards: [],
  chipyText: "",
  chipyStreaming: false,
  chipyPhase: "idle",
  chipyHandId: null,
  lastFinishedHandId: null,
  coachMode: loadCoachMode(),
  chipyDrillPrompt: null,
  pokerTournamentState: null,
  pokerCoachMode: loadPokerCoachMode(),
  pokerCoachText: "",
  pokerCoachStreaming: false,
  pokerCoachConfidenceTier: null,
  pokerCoachRecommendedAction: null,

  setTableState: (newState: TableState) => {
    set({ tableState: newState });
  },

  setMyHand: (hand: Hand | null) => {
    set({ myHand: hand });
  },

  openChipy: () => set({ chipyOpen: true }),
  closeChipy: () => set({ chipyOpen: false, chipyMessage: "", chipyLoading: false }),

  setChipyMessage: (message: string) => set({ chipyMessage: message }),
  setChipyLoading: (loading: boolean) => set({ chipyLoading: loading }),

  placeBet: (amount: number) => set({ betAmount: amount }),

  optimisticHit: (actionId: string) => {
    const { myHand } = get();
    if (!myHand) return;
    // null cast: Card | null is valid per Hand.cards type
    const placeholder: Card = { suit: "spades", value: "2" }; // sentinel face-down
    set({
      pendingActionId: actionId,
      pendingOptimisticCards: [placeholder],
      myHand: {
        ...myHand,
        cards: [...myHand.cards, null],
      },
    });
  },

  rollbackOptimistic: () => {
    const { myHand, pendingOptimisticCards } = get();
    if (!myHand) {
      set({ pendingActionId: null, pendingOptimisticCards: [] });
      return;
    }
    // Remove as many trailing nulls as we added as placeholders
    const countToRemove = pendingOptimisticCards.length;
    const realCards = myHand.cards.slice(0, myHand.cards.length - countToRemove);
    set({
      pendingActionId: null,
      pendingOptimisticCards: [],
      myHand: { ...myHand, cards: realCards },
    });
  },

  reconcileFromPoll: (newState: TableState, currentUserId: string) => {
    const { pendingActionId } = get();

    // Find the current user's hand in the polled state
    const serverHand = newState.hands.find((h) => h.user_id === currentUserId) ?? null;

    if (!pendingActionId) {
      // No pending optimistic update — just take the server state directly
      set({
        tableState: newState,
        myHand: serverHand,
      });
      return;
    }

    // There is a pending optimistic hit. Check if the server now has more
    // cards than before the optimistic hit (meaning the server processed it).
    const { myHand: currentHand } = get();
    const currentCardCount = currentHand?.cards.length ?? 0;
    const serverCardCount = serverHand?.cards.length ?? 0;

    if (serverCardCount >= currentCardCount) {
      // Server has caught up — clear the optimistic state and take server data
      set({
        tableState: newState,
        myHand: serverHand,
        pendingActionId: null,
        pendingOptimisticCards: [],
      });
    } else {
      // Server hasn't processed the action yet — keep optimistic hand,
      // but still update the rest of the table state
      set({ tableState: newState });
    }
  },

  beginChipyStream: (phase: "pre" | "post", handId: string) => {
    set({
      chipyText: "",
      chipyStreaming: true,
      chipyPhase: phase,
      chipyHandId: handId,
    });
  },

  appendChipyChunk: (chunk: string) => {
    set((state) => ({ chipyText: state.chipyText + chunk }));
  },

  endChipyStream: () => {
    set({ chipyStreaming: false });
  },

  resetChipy: () => {
    set({
      chipyText: "",
      chipyStreaming: false,
      chipyPhase: "idle",
      chipyHandId: null,
    });
  },

  setLastFinishedHandId: (handId: string | null) => {
    set({ lastFinishedHandId: handId });
  },

  setCoachMode: (mode: "quick" | "drill") => {
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(COACH_MODE_STORAGE_KEY, mode);
      } catch {
        // Swallow storage errors; in-memory state still updates below.
      }
    }
    set({ coachMode: mode });
  },

  setChipyDrillPrompt: (prompt: string | null) => {
    set({ chipyDrillPrompt: prompt });
  },

  // ─── Texas Hold'em actions ────────────────────────────────────────────────
  setPokerTournamentState: (state: PokerTournamentState | null) => {
    set({ pokerTournamentState: state });
  },
  setPokerCoachMode: (mode: "reads" | "odds") => {
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(POKER_COACH_MODE_STORAGE_KEY, mode);
      } catch {
        // ignore
      }
    }
    set({ pokerCoachMode: mode });
  },
  appendPokerCoachChunk: (text: string) => {
    set((s) => ({ pokerCoachText: s.pokerCoachText + text }));
  },
  beginPokerCoachStream: () => {
    set({
      pokerCoachText: "",
      pokerCoachStreaming: true,
      pokerCoachConfidenceTier: null,
      pokerCoachRecommendedAction: null,
    });
  },
  endPokerCoachStream: (
    confidenceTier: "DETERMINISTIC" | "HEURISTIC" | null,
    recommendedAction: string | null,
  ) => {
    set({
      pokerCoachStreaming: false,
      pokerCoachConfidenceTier: confidenceTier,
      pokerCoachRecommendedAction: recommendedAction,
    });
  },
  resetPokerCoach: () => {
    set({
      pokerCoachText: "",
      pokerCoachStreaming: false,
      pokerCoachConfidenceTier: null,
      pokerCoachRecommendedAction: null,
    });
  },
}));
