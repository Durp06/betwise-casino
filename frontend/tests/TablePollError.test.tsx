/**
 * TablePollError.test.tsx — T6 (M4) AC-6.1
 *
 * Table.tsx: with GET /api/tables/:id/state always returning an error,
 * after the poll failure threshold the page must render role="alert" (error
 * panel) and a Back-to-lobby / Retry control — NOT a permanent role="status"
 * aria-busy spinner.
 *
 * This test FAILS until useTablePoll accepts an `onError` callback and Table.tsx
 * replaces the unconditional spinner branch with an error panel when pollError is set.
 *
 * Failure mode (pre-fix): waitFor times out because role="alert" never appears —
 * the page stays on the "Pulling up a chair..." spinner forever.
 */
import { render, screen, waitFor, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, describe, it, expect, vi } from "vitest";

// ── Hoist mocks before vi.mock factories ─────────────────────────────────────
const { leaveTableMock } = vi.hoisted(() => ({
  leaveTableMock: vi.fn().mockResolvedValue({ data: { message: "left" }, error: null }),
}));

vi.mock("../src/api/client", () => ({
  leaveTable: leaveTableMock,
  // Always fail the state poll — this is the condition under test
  getTableState: vi.fn().mockResolvedValue({ data: null, error: "HTTP 500" }),
  // BalanceHeader (in Table's header) fetches the bankroll on mount — stub it so
  // it renders the balance (not an error alert that would clash with the poll alert).
  getMe: vi.fn().mockResolvedValue({
    data: {
      id: "u", username: "tester", chip_balance: 5_000_000, total_hands: 0,
      correct_decisions: 0, accuracy: 0, current_streak: 0, best_streak: 0,
      created_at: "2026-06-03T00:00:00Z",
    },
    error: null,
  }),
  streamPreAdvice: vi.fn(async (_: string, __: (t: string) => void, onDone: () => void) => {
    onDone();
  }),
  streamAdvice: vi.fn(),
  dealHand: vi.fn().mockResolvedValue({ data: null, error: null }),
  takeAction: vi.fn().mockResolvedValue({ data: null, error: null }),
  getHandActions: vi.fn().mockResolvedValue({ data: [], error: null }),
  getSessionReview: vi.fn().mockResolvedValue({ data: null, error: null }),
  gradePractice: vi.fn().mockResolvedValue({ data: null, error: null }),
  getChatMessages: vi.fn().mockResolvedValue({ data: [], error: null }),
  postChatMessage: vi.fn().mockResolvedValue({ data: null, error: null }),
}));

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

import Table from "../src/pages/Table";

afterEach(() => {
  vi.clearAllMocks();
});

function renderTable() {
  return render(
    <MemoryRouter initialEntries={["/table/t1"]}>
      <Routes>
        <Route path="/table/:id" element={<Table />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Table.tsx — poll failure surface (AC-6.1)", () => {
  // 14 s test timeout: poll cadence is 3 s, need ≥3 failures (≥9 s), plus headroom
  it(
    "shows an error panel (role=alert) after sustained /state failures, NOT a permanent spinner",
    async () => {
      renderTable();

      // Let the component mount and poll once
      await act(async () => {
        await new Promise((r) => setTimeout(r, 100));
      });

      // Assert that role="alert" appears within 12 s (after 3 poll failures at 3 s cadence).
      // Pre-fix this will time out because the hook silently swallows errors.
      await waitFor(
        () => {
          const alert = screen.queryByRole("alert");
          expect(alert).not.toBeNull();
        },
        { timeout: 11_000 },
      );

      // The page must not be stuck on an aria-busy spinner without an error panel
      const spinner = document.querySelector("[aria-busy='true']");
      if (spinner) {
        expect(screen.queryByRole("alert")).not.toBeNull();
      }

      // A Back-to-lobby or Retry affordance must be reachable
      const control =
        screen.queryByRole("button") ??
        screen.queryByRole("link");
      expect(control).not.toBeNull();
    },
    14_000,
  );
});
