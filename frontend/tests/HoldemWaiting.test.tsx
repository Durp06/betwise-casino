/**
 * HoldemWaiting.test.tsx — the "waiting for players" liveliness state.
 *
 * Hold'em is human-vs-human: a player seated alone can't deal (needs ≥2) and has
 * no opponent to animate, so the felt must not sit dead. When seated with <2
 * players and no active hand, HoldemTablePage shows a WaitingForPlayers panel;
 * once a second player sits, the panel gives way to the Deal button.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, describe, it, expect, vi, type Mock } from "vitest";
import type { HoldemTableState } from "../src/types";

vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/client")>();
  return {
    ...actual,
    getHoldemTableState: vi.fn(),
    leaveHoldemTable: vi.fn().mockResolvedValue({ data: { status: "left" }, error: null }),
    dealHoldemHand: vi.fn().mockResolvedValue({ data: null, error: null }),
    holdemAction: vi.fn().mockResolvedValue({ data: null, error: null }),
    getChatMessages: vi.fn().mockResolvedValue({ data: [], error: null }),
    postChatMessage: vi.fn().mockResolvedValue({ data: null, error: null }),
  };
});

vi.mock("../src/auth/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
    },
  },
  useSession: vi.fn().mockReturnValue({
    session: { user: { id: "dev-user" } },
    loading: false,
  }),
}));

import { getHoldemTableState } from "../src/api/client";
import { useGameStore } from "../src/store/gameStore";
import HoldemTablePage from "../src/pages/HoldemTablePage";

/** A seated table state with `seatCount` active players (you are seat 0), no hand. */
function seatedState(seatCount: number): HoldemTableState {
  const seats = [
    { id: "s0", user_id: "dev-user", seat_number: 0, stack: 2000, status: "active", username: "dev" },
  ];
  if (seatCount >= 2) {
    seats.push({ id: "s1", user_id: "other", seat_number: 1, stack: 2000, status: "active", username: "botsy" });
  }
  return {
    table: {
      id: "tbl-1",
      name: "Test Table",
      small_blind: 50,
      big_blind: 100,
      min_buy_in: 2000,
      max_buy_in: 20000,
      max_seats: 6,
      status: "open",
      created_at: "2026-01-01T00:00:00Z",
    },
    seats,
    current_hand: null,
    your_seat_number: null,
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

afterEach(() => {
  vi.clearAllMocks();
  useGameStore.getState().setHoldemTableState(null);
});

describe("HoldemTablePage — waiting-for-players liveliness", () => {
  it("shows the waiting panel when seated alone (<2 players, no hand)", async () => {
    (getHoldemTableState as Mock).mockResolvedValue({ data: seatedState(1), error: null });
    renderPage();

    expect(await screen.findByTestId("holdem-waiting-for-players")).toBeInTheDocument();
    // No hand can be dealt with one player, so no Deal button.
    expect(screen.queryByTestId("holdem-deal-button")).toBeNull();
  });

  it("replaces the waiting panel with the Deal button once a second player sits", async () => {
    (getHoldemTableState as Mock).mockResolvedValue({ data: seatedState(2), error: null });
    renderPage();

    expect(await screen.findByTestId("holdem-deal-button")).toBeInTheDocument();
    expect(screen.queryByTestId("holdem-waiting-for-players")).toBeNull();
  });
});
