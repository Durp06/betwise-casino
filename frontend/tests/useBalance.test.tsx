/**
 * useBalance.test.tsx — Frontend AC-F1.
 *
 * Tests that useBalance() exposes { balance, loading, error, refresh() } and
 * honours the two key contracts:
 *   AC-F1 success: calling refresh() fetches GET /api/users/me, writes
 *                  chip_balance to the store, sets loading=false, error=null.
 *   AC-F1 error:   when getMe() returns { error }, the hook stores the error
 *                  message AND leaves any previously-set balance untouched.
 *
 * HTTP is mocked with MSW following the ChipyPanel.test.tsx setupServer pattern.
 * The real walletStore + useBalance hook are exercised; no Zustand internals are
 * mocked.
 */

import { renderHook, act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { beforeAll, afterAll, afterEach, describe, it, expect } from "vitest";

// These modules do not exist yet — expected to fail with "Cannot find module"
// until the implementer creates them.
import { useBalance } from "../src/hooks/useBalance";

// ─── Fixture ──────────────────────────────────────────────────────────────────

const ME_SUCCESS = {
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

const server = setupServer(
  http.get("/api/users/me", () => HttpResponse.json(ME_SUCCESS)),
);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("AC-F1: useBalance() refresh success — stores chip_balance", () => {
  it("after refresh(), balance equals the server chip_balance, loading is false, error is null", async () => {
    const { result } = renderHook(() => useBalance());

    // Trigger refresh
    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.balance).toBe(5_000_000);
    expect(result.current.error).toBeNull();
  });
});

describe("AC-F1: useBalance() refresh error — keeps prior balance, sets error", () => {
  it("on a 500 response, error is set and a previously stored balance is preserved", async () => {
    // Seed a successful balance first so there IS a prior balance to preserve.
    const { result } = renderHook(() => useBalance());

    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => {
      expect(result.current.balance).toBe(5_000_000);
    });

    // Now make the server return an error
    server.use(
      http.get("/api/users/me", () =>
        HttpResponse.json({ detail: "Internal Server Error" }, { status: 500 }),
      ),
    );

    await act(async () => {
      await result.current.refresh();
    });

    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    // The prior balance must NOT have been wiped
    expect(result.current.balance).toBe(5_000_000);
  });
});
