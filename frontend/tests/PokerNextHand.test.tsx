/**
 * PokerNextHand.test.tsx — regression for "poker doesn't deal again".
 *
 * Bug: PokerTablePage deals a hand only on mount; usePokerPoll only GETs
 * /state; the backend marks a finished hand `complete` and waits for the
 * client to re-call /deal. Nothing did, so after hand #1 the SNG froze on
 * "Hand complete. Next hand will be dealt shortly."
 *
 * AC-1: when the current hand is `complete` and the tournament is still
 *       active, the page calls dealPokerHand again (deals the next hand).
 * AC-2: when the tournament is `complete`, the page does NOT auto-deal and
 *       shows a tournament-over affordance.
 */
import { render, screen, waitFor, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";

const h = vi.hoisted(() => {
  function makeState(handStatus: string, tournamentStatus: string, handId = "h1") {
    return {
      tournament: {
        id: "t1", bot_count: 3, advice_mode: "odds", buy_in_cents: 5000,
        starting_stack_chips: 1500, hands_per_level: 10, status: tournamentStatus,
        button_seat: 0, current_hand_number: 1, created_at: "2026-01-01T00:00:00Z",
      },
      seats: [
        { user_id: "dev-user", seat_number: 0, archetype_name: null, starting_stack: 1500, current_stack: 1500, is_bust: false, is_bot: false },
        { user_id: null, seat_number: 1, archetype_name: "TAG", starting_stack: 1500, current_stack: 1500, is_bust: false, is_bot: true },
      ],
      current_hand: {
        id: handId, hand_number: 1, button_seat: 0, small_blind: 10, big_blind: 20, ante: 0,
        board: [], pot_total: 30, side_pots: [],
        street: handStatus === "complete" ? "complete" : "preflop",
        current_bet_to_match: 20,
        current_to_act_seat: handStatus === "complete" ? null : 0,
        last_aggressor_seat: null, min_raise_increment: 20, status: handStatus,
        seats: [
          { seat_number: 0, hole_cards: [{ suit: "spades", value: "2" }, { suit: "hearts", value: "Q" }], starting_stack: 1500, final_stack: 1480, current_bet: 0, is_folded: handStatus === "complete", is_all_in: false },
          { seat_number: 1, hole_cards: [null, null], starting_stack: 1500, final_stack: 1520, current_bet: 0, is_folded: false, is_all_in: false },
        ],
        actions: [],
      },
      your_seat_number: 0,
    };
  }
  const holder: { result: unknown } = { result: null };
  return { makeState, holder };
});

vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/client")>();
  return {
    ...actual,
    dealPokerHand: vi.fn(async () => ({ data: h.holder.result, error: null })),
    getPokerTournamentState: vi.fn(async () => ({ data: h.holder.result, error: null })),
    pokerAction: vi.fn().mockResolvedValue({ data: null, error: null }),
    getChatMessages: vi.fn().mockResolvedValue({ data: [], error: null }),
    postChatMessage: vi.fn().mockResolvedValue({ data: null, error: null }),
  };
});

vi.mock("../src/auth/supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }), onAuthStateChange: vi.fn().mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } }) } },
  useSession: vi.fn().mockReturnValue({ session: { user: { id: "dev-user" } }, loading: false }),
}));

import PokerTablePage from "../src/pages/PokerTablePage";
import { dealPokerHand } from "../src/api/client";
import { useGameStore } from "../src/store/gameStore";

beforeEach(() => {
  useGameStore.getState().setPokerTournamentState(null);
});
afterEach(() => {
  vi.clearAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/poker/t1"]}>
      <Routes>
        <Route path="/poker/:id" element={<PokerTablePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PokerTablePage — deals the next hand after one completes", () => {
  it("AC-1: re-calls dealPokerHand when the current hand is complete and tournament is active", async () => {
    h.holder.result = h.makeState("complete", "active");
    renderPage();

    // Mount deal is call #1. The fix must fire a SECOND deal once it sees the
    // completed hand. Pre-fix: stays at 1 forever → this times out (RED).
    await waitFor(
      () => { expect(vi.mocked(dealPokerHand).mock.calls.length).toBeGreaterThanOrEqual(2); },
      { timeout: 6000 },
    );
  }, 8000);

  it("AC-2: does NOT auto-deal when the tournament is complete; shows tournament-over UI", async () => {
    h.holder.result = h.makeState("complete", "complete");
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId("poker-tournament-over")).toBeInTheDocument();
    });

    // Give the (would-be) auto-deal timer time to fire, then assert it did NOT:
    // only the single mount deal happened.
    await new Promise((r) => setTimeout(r, 2600));
    expect(vi.mocked(dealPokerHand).mock.calls.length).toBe(1);
  }, 8000);

  it("AC-3: a poll re-render during the delay does NOT cancel the pending auto-deal", async () => {
    // Regression for the timer-cancel race: the 3s poll re-delivers the same
    // completed hand as a NEW object; if the effect depends on the whole state
    // object, that re-render's cleanup kills the pending deal and it never fires.
    h.holder.result = h.makeState("complete", "active", "h1");
    renderPage();

    // Let mount-deal land + the auto-deal get scheduled (delay is 2200ms).
    await new Promise((r) => setTimeout(r, 700));
    const before = vi.mocked(dealPokerHand).mock.calls.length;

    // Simulate a /state poll arriving mid-delay: push a fresh (equal) completed
    // state object into the store, forcing a re-render.
    await act(async () => {
      useGameStore.getState().setPokerTournamentState(
        h.makeState("complete", "active", "h1") as never,
      );
    });

    // The scheduled deal must still fire despite the mid-delay re-render.
    await waitFor(
      () => { expect(vi.mocked(dealPokerHand).mock.calls.length).toBeGreaterThan(before); },
      { timeout: 4000 },
    );
  }, 9000);
});
