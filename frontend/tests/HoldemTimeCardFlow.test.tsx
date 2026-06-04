/**
 * HoldemTimeCardFlow.test.tsx — integration: clicking "+15s" on the live table
 * spends a card and the decremented count propagates store → component.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { HoldemTableState } from "../src/types";

vi.mock("../src/hooks/useHoldemPoll", () => ({ useHoldemPoll: () => {} }));
vi.mock("../src/auth/supabase", () => ({
  useSession: () => ({ session: { user: { id: "me" } } }),
}));
// HoldemActionBar/ChatPanel aren't under test here — stub so the felt mounts cleanly.
vi.mock("../src/components/HoldemActionBar", () => ({ default: () => null }));
vi.mock("../src/components/ChatPanel", () => ({ default: () => null }));

const { useHoldemTimeCardMock } = vi.hoisted(() => ({ useHoldemTimeCardMock: vi.fn() }));
vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/client")>();
  return {
    ...actual,
    useHoldemTimeCard: useHoldemTimeCardMock,
    getHoldemTableState: vi.fn(async () => ({ data: makeState(5), error: null })),
    leaveHoldemTable: vi.fn(async () => ({ data: { status: "left" }, error: null })),
  };
});

import HoldemTablePage from "../src/pages/HoldemTablePage";
import { useGameStore } from "../src/store/gameStore";

function makeState(cards: number): HoldemTableState {
  return {
    table: {
      id: "tbl-1", name: "T", small_blind: 50, big_blind: 100,
      min_buy_in: 2_000, max_buy_in: 20_000, max_seats: 6, status: "playing",
      created_at: new Date("2026-06-03T12:00:00Z").toISOString(),
    },
    seats: [
      { id: "s1", user_id: "me", seat_number: 0, stack: 9_900, status: "active", username: "me" },
    ],
    current_hand: {
      id: "h1", hand_number: 1, button_seat: 0, small_blind: 50, big_blind: 100,
      board: [], pot_total: 150, side_pots: [], street: "preflop",
      current_bet_to_match: 100, current_to_act_seat: 0, last_aggressor_seat: null,
      min_raise_increment: 100,
      move_deadline_at: new Date("2026-06-03T12:00:30Z").toISOString(),
      status: "active", result: null,
      seats: [
        {
          seat_number: 0, table_seat_number: 0, user_id: "me", username: "me",
          hole_cards: [{ suit: "hearts", value: "A" }, { suit: "spades", value: "K" }],
          starting_stack: 10_000, final_stack: 9_900, current_bet: 50,
          is_folded: false, is_all_in: false,
        },
      ],
      actions: [],
    },
    your_seat_number: 0,
    your_time_cards_remaining: cards,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/holdem/table/tbl-1"]}>
      <Routes>
        <Route path="/holdem/table/:id" element={<HoldemTablePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("HoldemTablePage — time-card flow", () => {
  beforeEach(() => {
    useHoldemTimeCardMock.mockReset();
    useGameStore.setState({ holdemTableState: makeState(5) });
  });
  afterEach(() => {
    useGameStore.setState({ holdemTableState: null });
  });

  it("spending a card updates the displayed count from 5/5 to 4/5", async () => {
    useHoldemTimeCardMock.mockResolvedValue({ data: makeState(4), error: null });
    renderPage();

    expect(screen.getByTestId("time-card-control")).toHaveTextContent("5/5");

    fireEvent.click(screen.getByTestId("time-card-use"));

    await waitFor(() => {
      expect(screen.getByTestId("time-card-control")).toHaveTextContent("4/5");
    });
    expect(useHoldemTimeCardMock).toHaveBeenCalledWith("tbl-1");
  });
});
