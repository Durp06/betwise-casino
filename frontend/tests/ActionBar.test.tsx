/**
 * ActionBar.test.tsx — the SILVER "optimistic update with rollback" box.
 *
 * Hit must update the UI *before* the server confirms (a face-down placeholder
 * card appears immediately) and must roll that placeholder back if the request
 * fails. The optimistic machinery already lives in gameStore
 * (optimisticHit / rollbackOptimistic / settleOptimistic); these tests pin that
 * ActionBar actually drives it, not just that the store can.
 */
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ActionBar from "../src/components/ActionBar";
import { useGameStore } from "../src/store/gameStore";
import type { Hand } from "../src/types";

const { takeActionMock, streamAdviceMock } = vi.hoisted(() => ({
  takeActionMock: vi.fn(),
  streamAdviceMock: vi.fn(),
}));
vi.mock("../src/api/client", () => ({
  takeAction: takeActionMock,
  streamAdvice: streamAdviceMock,
}));

function makeHand(overrides: Partial<Hand> = {}): Hand {
  return {
    id: "hand-1",
    session_id: "s1",
    user_id: "u1",
    cards: [
      { suit: "hearts", value: "10" },
      { suit: "spades", value: "6" },
    ],
    bet: 500,
    status: "active",
    outcome: null,
    payout: null,
    move_deadline_at: null,
    ...overrides,
  };
}

const THREE_CARD_HAND = makeHand({
  cards: [
    { suit: "hearts", value: "10" },
    { suit: "spades", value: "6" },
    { suit: "clubs", value: "4" },
  ],
});

beforeEach(() => {
  takeActionMock.mockReset();
  streamAdviceMock.mockReset();
  streamAdviceMock.mockResolvedValue(undefined);
  useGameStore.setState({
    myHand: makeHand(),
    pendingActionId: null,
    pendingOptimisticCards: [],
  } as Parameters<typeof useGameStore.setState>[0]);
});

describe("ActionBar — optimistic Hit + rollback (silver)", () => {
  it("appends a face-down placeholder and sets pendingActionId BEFORE the server responds", async () => {
    // Keep takeAction in-flight so we can observe the optimistic state.
    let resolve!: (v: { data: Hand | null; error: string | null }) => void;
    takeActionMock.mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );

    render(<ActionBar tableId="t1" legalActions={["hit", "stand", "double"]} isMyTurn handId="hand-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Hit" }));

    await waitFor(() => {
      const s = useGameStore.getState();
      expect(s.myHand?.cards).toHaveLength(3); // optimistic card added
      expect(s.myHand?.cards[2]).toBeNull(); // rendered face-down
      expect(s.pendingActionId).not.toBeNull();
    });

    // Let it settle so no state update happens after the test ends.
    await act(async () => {
      resolve({ data: THREE_CARD_HAND, error: null });
    });
    await waitFor(() => expect(useGameStore.getState().pendingActionId).toBeNull());
  });

  it("rolls the placeholder back and surfaces the error when the Hit fails", async () => {
    takeActionMock.mockResolvedValue({ data: null, error: "Not your turn" });

    render(<ActionBar tableId="t1" legalActions={["hit", "stand", "double"]} isMyTurn handId="hand-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Hit" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Not your turn"));
    const s = useGameStore.getState();
    expect(s.myHand?.cards).toHaveLength(2); // placeholder removed (no phantom card)
    expect(s.pendingActionId).toBeNull();
  });

  it("settles to the server hand and clears pending on success", async () => {
    takeActionMock.mockResolvedValue({ data: THREE_CARD_HAND, error: null });

    render(<ActionBar tableId="t1" legalActions={["hit", "stand", "double"]} isMyTurn handId="hand-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Hit" }));

    await waitFor(() => {
      const s = useGameStore.getState();
      expect(s.myHand?.cards).toHaveLength(3);
      expect(s.myHand?.cards[2]).toEqual({ suit: "clubs", value: "4" }); // real card, not the null placeholder
      expect(s.pendingActionId).toBeNull();
    });
  });
});
