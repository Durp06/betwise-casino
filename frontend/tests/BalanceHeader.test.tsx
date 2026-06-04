/**
 * BalanceHeader.test.tsx — Frontend AC-F2 and AC-F3.
 *
 *   AC-F2: given a wallet balance of 5_000_000, the rendered output contains
 *          "$50,000" (formatMoney contract verified in money.test.ts).
 *   AC-F3: while loading=true and balance=null a role="status" element is shown;
 *          when error is set and balance=null a role="alert" element is shown —
 *          no happy-path-only render.
 *
 * Strategy: the walletStore is seeded directly (via the store's own setter) to
 * drive each display state, so the tests are not coupled to network timing.
 * MSW is set up for completeness (BalanceHeader may call refresh on mount).
 */

import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { beforeAll, afterAll, afterEach, describe, it, expect } from "vitest";

// These modules do not exist yet — expected to fail with "Cannot find module"
// until the implementer creates them.
import BalanceHeader from "../src/components/BalanceHeader";
import { useWalletStore } from "../src/store/walletStore";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const ME_LOADED = {
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

// ─── MSW server ───────────────────────────────────────────────────────────────

// By default let /api/users/me return a success so that any on-mount fetch in
// BalanceHeader doesn't cause unhandled-request noise.
const server = setupServer(
  http.get("/api/users/me", () => HttpResponse.json(ME_LOADED)),
);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => {
  server.resetHandlers();
  // Reset store to a clean slate between tests so state doesn't bleed.
  useWalletStore.setState({ balance: null, loading: false, error: null });
});
afterAll(() => server.close());

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("AC-F2: BalanceHeader renders formatted balance", () => {
  it('shows "$50,000" when the wallet balance is 5_000_000', async () => {
    // Seed the store with the loaded balance so there is no async delay.
    useWalletStore.setState({ balance: 5_000_000, loading: false, error: null });

    render(<BalanceHeader />);

    await waitFor(() => {
      expect(screen.getByText("$50,000")).toBeInTheDocument();
    });
  });
});

describe("AC-F3: BalanceHeader shows loading and error states (no happy-path-only render)", () => {
  it('renders role="status" when loading is true and balance is null', () => {
    useWalletStore.setState({ balance: null, loading: true, error: null });

    render(<BalanceHeader />);

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it('renders role="alert" when error is set and balance is null', () => {
    useWalletStore.setState({
      balance: null,
      loading: false,
      error: "Network error — please retry",
    });

    render(<BalanceHeader />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
