/**
 * store/paiGowStore.ts — Zustand store for Pai Gow Poker game state.
 *
 * Lives entirely separate from `gameStore.ts` (blackjack) per the
 * round-7 owner direction. No shared state. PG-specific pages
 * import this directly; existing blackjack pages do not.
 *
 * The store covers:
 * - `tableState`: the polled PaiGowTableState; the source of truth between
 *   polls. Updated by the 3s polling hook.
 * - `myHand`: derived from `tableState.hands` by current user id; convenience
 *   for components that only care about the owner's hand.
 * - `frontDraft`: the cards the player has tentatively placed into the front
 *   2-card hand inside HandSetter. Driven by tap-to-assign UX.
 * - Chipy SSE state: text, streaming flag, phase, hand id. Renders into
 *   `ChipyPaiGowCoach`.
 * - Pre-set + post-set Chipy summaries: the final JSON event surfaced by
 *   the streaming endpoint. Used to highlight the recommended split (pre)
 *   and the celebratory "you played it right / EV loss X" banner (post).
 */
import { create } from "zustand";
import type {
  PaiGowAdvicePostSummary,
  PaiGowAdvicePreSummary,
  PaiGowCard,
  PaiGowPlayerHand,
  PaiGowTableState,
} from "../types";

interface PaiGowState {
  /** Latest polled PG table state. Null before the first poll completes. */
  tableState: PaiGowTableState | null;

  /** Convenience: the current user's hand on the active round. */
  myHand: PaiGowPlayerHand | null;

  /** Cards the player has tentatively assigned to the front (2-card) hand
   *  inside `HandSetter`. Order doesn't matter — round-7 hand-strength
   *  comparison in optimal_set.evaluate_split is order-independent. */
  frontDraft: PaiGowCard[];

  /** Chipy SSE state. */
  chipyText: string;
  chipyStreaming: boolean;
  chipyPhase: "idle" | "pre" | "post";
  chipyHandId: string | null;

  /** Pre-set Chipy summary (the optimal split). Drives the "recommended"
   *  visual hint in HandSetter. */
  preOptimal: PaiGowAdvicePreSummary | null;

  /** Post-set Chipy evaluation result. Used for the post-play banner. */
  postEvaluation: PaiGowAdvicePostSummary | null;

  /** ID of the most recent hand the local player saw finish during this
   *  visit. Gates the celebratory banner so a stale finished hand from a
   *  prior session doesn't fire on fresh join. */
  lastFinishedHandId: string | null;
}

interface PaiGowActions {
  /** Replace the entire table state. Called by the polling hook on each
   *  successful response. Also recomputes `myHand`. */
  setTableState: (state: PaiGowTableState, currentUserId: string) => void;

  /** Clear table state — used on page unmount / leave. */
  clearTableState: () => void;

  /** HandSetter — assign / unassign a card to/from the 2-card front. */
  toggleFrontCard: (card: PaiGowCard) => void;

  /** Wipe the front draft. Called when a new hand is dealt or after submit. */
  clearFrontDraft: () => void;

  /** Chipy SSE controls. */
  beginChipyStream: (phase: "pre" | "post", handId: string) => void;
  appendChipyChunk: (chunk: string) => void;
  endChipyStream: () => void;
  resetChipy: () => void;
  setPreOptimal: (summary: PaiGowAdvicePreSummary | null) => void;
  setPostEvaluation: (summary: PaiGowAdvicePostSummary | null) => void;

  /** Mark the last hand the local player saw finish. */
  setLastFinishedHandId: (handId: string | null) => void;
}

/** Cards are dict-shaped; compare by suit+value for tap-to-assign equality. */
function cardKey(c: PaiGowCard): string {
  return `${c.suit}:${c.value}`;
}

export const usePaiGowStore = create<PaiGowState & PaiGowActions>((set, get) => ({
  tableState: null,
  myHand: null,
  frontDraft: [],
  chipyText: "",
  chipyStreaming: false,
  chipyPhase: "idle",
  chipyHandId: null,
  preOptimal: null,
  postEvaluation: null,
  lastFinishedHandId: null,

  setTableState: (state, currentUserId) => {
    const myHand =
      state.hands.find((h) => h.user_id === currentUserId) ?? null;

    // If a new hand was dealt (different hand id or no previous), reset
    // the front draft + chipy state for the fresh round.
    const prevMyHand = get().myHand;
    const newHandStarted =
      myHand !== null &&
      (prevMyHand === null || prevMyHand.id !== myHand.id);

    set({
      tableState: state,
      myHand,
      ...(newHandStarted
        ? {
            frontDraft: [],
            chipyText: "",
            chipyStreaming: false,
            chipyPhase: "idle",
            chipyHandId: null,
            preOptimal: null,
            postEvaluation: null,
          }
        : {}),
    });
  },

  clearTableState: () =>
    set({
      tableState: null,
      myHand: null,
      frontDraft: [],
      chipyText: "",
      chipyStreaming: false,
      chipyPhase: "idle",
      chipyHandId: null,
      preOptimal: null,
      postEvaluation: null,
      lastFinishedHandId: null,
    }),

  toggleFrontCard: (card) => {
    const { frontDraft } = get();
    const key = cardKey(card);
    const isPresent = frontDraft.some((c) => cardKey(c) === key);
    if (isPresent) {
      set({ frontDraft: frontDraft.filter((c) => cardKey(c) !== key) });
      return;
    }
    // Cap the front draft at 2 cards — any further tap is a no-op.
    if (frontDraft.length >= 2) return;
    set({ frontDraft: [...frontDraft, card] });
  },

  clearFrontDraft: () => set({ frontDraft: [] }),

  beginChipyStream: (phase, handId) =>
    set({
      chipyText: "",
      chipyStreaming: true,
      chipyPhase: phase,
      chipyHandId: handId,
    }),
  appendChipyChunk: (chunk) =>
    set((s) => ({ chipyText: s.chipyText + chunk })),
  endChipyStream: () => set({ chipyStreaming: false }),
  resetChipy: () =>
    set({
      chipyText: "",
      chipyStreaming: false,
      chipyPhase: "idle",
      chipyHandId: null,
    }),
  setPreOptimal: (summary) => set({ preOptimal: summary }),
  setPostEvaluation: (summary) => set({ postEvaluation: summary }),

  setLastFinishedHandId: (handId) => set({ lastFinishedHandId: handId }),
}));
