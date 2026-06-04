/**
 * BalanceRefresh.test.tsx — Frontend AC-F5 and AC-F6.
 *
 *   AC-F5: on mount of BalanceHeader (the balance surface), GET /api/users/me
 *          is requested exactly once and the formatted balance appears.
 *   AC-F6: after a money-moving action the wallet store's refresh() is called
 *          again, a SECOND GET /api/users/me fires, and the displayed balance
 *          updates to the server's new value (no stale balance).
 *
 * Both tests are driven at the store/hook level using BalanceHeader as the
 * rendering surface, so they are independent of full page wiring.
 *
 * MSW request counting via an in-handler counter spy follows the
 * ChipyPanel.test.tsx pattern.
 */

import { render, screen, waitFor, act } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { beforeAll, afterAll, afterEach, describe, it, expect } from "vitest";

// These modules do not exist yet — expected to fail with "Cannot find module"
// until the implementer creates them.
import BalanceHeader from "../src/components/BalanceHeader";
import { useWalletStore } from "../src/store/walletStore";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const ME_INITIAL = {
  id: "user-abc",
  username: "tester",
  chip_balance: 5_000_000,
  total_hands: 0,
  correct_decisions: 0,
  accuracy: 0,
  current_streak: 0,
  best_streak: 0,
  created_at: "2026-06-03T00:00:00Z",
};

const ME_AFTER_BET = {
  ...ME_INITIAL,
  chip_balance: 4_990_000, // lost a bet
};

// ─── MSW server ───────────────────────────────────────────────────────────────

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => {
  server.resetHandlers();
  useWalletStore.setState({ balance: null, loading: false, error: null });
});
afterAll(() => server.close());

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("AC-F5: balance surface fetches on mount and displays the balance", () => {
  it("requests GET /api/users/me once on mount and shows the formatted balance", async () => {
    let callCount = 0;

    server.use(
      http.get("/api/users/me", () => {
        callCount += 1;
        return HttpResponse.json(ME_INITIAL);
      }),
    );

    render(<BalanceHeader />);

    // The balance must eventually appear after the on-mount fetch
    await waitFor(() => {
      expect(screen.getByText("$50,000")).toBeInTheDocument();
    });

    // Exactly one request fired during mount
    expect(callCount).toBe(1);
  });
});

describe("AC-F6: balance updates after a money-moving action triggers refresh()", () => {
  it("a second getMe() fires after refresh() and the displayed balance updates", async () => {
    let callCount = 0;

    // First call returns initial balance; second returns the post-action balance.
    server.use(
      http.get("/api/users/me", () => {
        callCount += 1;
        if (callCount === 1) {
          return HttpResponse.json(ME_INITIAL);
        }
        return HttpResponse.json(ME_AFTER_BET);
      }),
    );

    render(<BalanceHeader />);

    // Wait for the initial mount fetch to complete
    await waitFor(() => {
      expect(screen.getByText("$50,000")).toBeInTheDocument();
    });

    expect(callCount).toBe(1);

    // Simulate a money-moving action completing: the handler calls refresh()
    await act(async () => {
      await useWalletStore.getState().refresh();
    });

    // A second request must have fired
    await waitFor(() => {
      expect(callCount).toBe(2);
    });

    // The displayed balance must update to the new server value
    // ME_AFTER_BET.chip_balance = 4_990_000 → formatMoney → "$49,900"
    await waitFor(() => {
      expect(screen.getByText("$49,900")).toBeInTheDocument();
    });

    // The stale "$50,000" must no longer be displayed
    expect(screen.queryByText("$50,000")).not.toBeInTheDocument();
  });
});
