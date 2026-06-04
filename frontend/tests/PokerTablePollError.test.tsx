/**
 * PokerTablePollError.test.tsx — T6 (M4) AC-6.3
 *
 * PokerTablePage.tsx: with GET /api/poker/tournaments/:id/state always failing
 * (but the initial deal succeeding), after the failure threshold the page renders
 * role="alert" and a Back-to-lobby / Retry control — NOT a permanent spinner.
 *
 * This test FAILS until usePokerPoll accepts an `onError` callback and
 * PokerTablePage.tsx exposes an error panel when pollError is set.
 *
 * Failure mode (pre-fix): waitFor times out — the poll errors are silently
 * discarded so the page never transitions from its initial rendered state.
 */
import { render, screen, waitFor, within, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, describe, it, expect, vi } from "vitest";

// ── Hoist fake data before vi.mock factories ────────────────────────────────
const { fakeTournamentState } = vi.hoisted(() => ({
  fakeTournamentState: {
    tournament: {
      id: "t1",
      bot_count: 2,
      advice_mode: "odds",
      buy_in_cents: 1000,
      starting_stack_chips: 1500,
      hands_per_level: 10,
      status: "active",
      button_seat: 0,
      current_hand_number: 1,
      created_at: "2026-01-01T00:00:00Z",
    },
    seats: [
      {
        user_id: "dev-user",
        seat_number: 0,
        archetype_name: null,
        starting_stack: 1500,
        current_stack: 1500,
        is_bust: false,
        is_bot: false,
      },
    ],
    current_hand: null,
    your_seat_number: 0,
  },
}));

// ── Client mock — deal succeeds, state poll always fails ─────────────────────
vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/client")>();
  return {
    ...actual,
    dealPokerHand: vi.fn().mockResolvedValue({ data: fakeTournamentState, error: null }),
    getPokerTournamentState: vi.fn().mockResolvedValue({ data: null, error: "HTTP 500" }),
    pokerAction: vi.fn().mockResolvedValue({ data: null, error: null }),
    getChatMessages: vi.fn().mockResolvedValue({ data: [], error: null }),
    postChatMessage: vi.fn().mockResolvedValue({ data: null, error: null }),
    // BalanceHeader mounts in the page header and calls getMe on mount.
    // Return a success so it renders the balance (not a role="alert" error span)
    // which would otherwise satisfy the waitFor check before the poll-error
    // panel appears — causing queryByRole("button") to find multiple buttons.
    getMe: vi.fn().mockResolvedValue({
      data: {
        id: "u", username: "tester", chip_balance: 5_000_000, total_hands: 0,
        correct_decisions: 0, accuracy: 0, current_streak: 0, best_streak: 0,
        created_at: "2026-06-03T00:00:00Z",
      },
      error: null,
    }),
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

import PokerTablePage from "../src/pages/PokerTablePage";

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

describe("PokerTablePage — poll failure surface (AC-6.3)", () => {
  it(
    "shows error panel (role=alert) after sustained /state failures, NOT a permanent spinner",
    async () => {
      renderPage();

      // Let the deal complete and component render initial state
      await act(async () => {
        await new Promise((r) => setTimeout(r, 200));
      });

      // After N consecutive poll failures the hook must call onError; PokerTablePage
      // must render a role="alert" panel that itself contains a recovery control
      // (a Retry button / Back-to-lobby link) — NOT a permanent spinner. We assert
      // the alert and its recovery control together, scoped with within(), so the
      // query stays robust to the rest of the page rendering its own buttons (the
      // persistent balance header added by the money system). Pre-fix: the page
      // stays on its static state and no alert ever appears.
      await waitFor(
        () => {
          const alert = screen.getByRole("alert");
          const recovery =
            within(alert).queryByRole("button") ?? within(alert).queryByRole("link");
          expect(recovery).not.toBeNull();
        },
        { timeout: 11_000 },
      );

      // It must be the error panel, not a bare spinner: no aria-busy node remains.
      expect(document.querySelector("[aria-busy='true']")).toBeNull();
    },
    14_000,
  );
});
