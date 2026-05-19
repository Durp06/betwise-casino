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
}));
