/**
 * store/gameStore.ts — Zustand store for BetWise Casino game state.
 *
 * Silver feature: optimistic Hit with rollback.
 * Gold feature: pendingActionId guard prevents polling from double-applying
 *               an optimistic update that's already been sent to the server.
 */
import { create } from "zustand";
import type { Card, Hand, TableState } from "../types";

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
}));
