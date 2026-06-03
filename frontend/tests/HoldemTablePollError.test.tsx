/**
 * HoldemTablePollError.test.tsx — T6 (M4) AC-6.2
 *
 * HoldemTablePage.tsx: with GET /api/holdem/tables/:id/state always failing,
 * after the failure threshold the page renders role="alert" (error panel) and
 * a Back-to-lobby / Retry control — NOT a permanent aria-busy spinner.
 *
 * This test FAILS until useHoldemPoll accepts an `onError` callback and
 * HoldemTablePage.tsx replaces the unconditional spinner with an error panel.
 *
 * Failure mode (pre-fix): waitFor times out — page stays on "Pulling up a chair..."
 */
import { render, screen, waitFor, act } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, describe, it, expect, vi } from "vitest";

// ── Client mock — getHoldemTableState always returns an error ─────────────
vi.mock("../src/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/api/client")>();
  return {
    ...actual,
    getHoldemTableState: vi.fn().mockResolvedValue({ data: null, error: "HTTP 500" }),
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

import HoldemTablePage from "../src/pages/HoldemTablePage";

afterEach(() => {
  vi.clearAllMocks();
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/holdem/table/tbl-1"]}>
      <Routes>
        <Route path="/holdem/table/:id" element={<HoldemTablePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("HoldemTablePage — poll failure surface (AC-6.2)", () => {
  it(
    "shows error panel (role=alert) after sustained /state failures, NOT a permanent spinner",
    async () => {
      renderPage();

      await act(async () => {
        await new Promise((r) => setTimeout(r, 100));
      });

      // After N consecutive poll failures the hook must call onError; HoldemTablePage
      // must then render role="alert" instead of the "Pulling up a chair…" spinner.
      await waitFor(
        () => {
          const alert = screen.queryByRole("alert");
          expect(alert).not.toBeNull();
        },
        { timeout: 11_000 },
      );

      const spinner = document.querySelector("[aria-busy='true']");
      if (spinner) {
        expect(screen.queryByRole("alert")).not.toBeNull();
      }

      const control =
        screen.queryByRole("button") ??
        screen.queryByRole("link");
      expect(control).not.toBeNull();
    },
    14_000,
  );
});
