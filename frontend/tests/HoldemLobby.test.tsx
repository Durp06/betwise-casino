/**
 * HoldemLobby.test.tsx — AC-F3: the multiplayer Hold'em table browser shows
 * loading + list + error branches (CLAUDE.md: no happy-path-only components).
 * HTTP is mocked with MSW; React Router is provided via MemoryRouter.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router-dom";
import { beforeAll, beforeEach, afterAll, afterEach, describe, it, expect } from "vitest";
import HoldemLobby from "../src/pages/HoldemLobby";
import { useWalletStore } from "../src/store/walletStore";

const TABLE = {
  id: "tbl-1",
  name: "Felt Five",
  small_blind: 50,
  big_blind: 100,
  min_buy_in: 2_000,
  max_buy_in: 20_000,
  max_seats: 6,
  status: "waiting",
  seats_taken: 2,
};

// BalanceHeader calls GET /api/users/me on mount. Keep the MSW handler for the
// actual network call, and also pre-seed the walletStore with a non-null balance
// before each test so BalanceHeader renders the balance display immediately (no
// role="status" loading span) and doesn't conflict with the page's own loading
// skeleton which also uses role="status".
const ME_RESPONSE = {
  id: "u1",
  username: "tester",
  chip_balance: 5_000_000,
  total_hands: 0,
  correct_decisions: 0,
  accuracy: 0,
  current_streak: 0,
  best_streak: 0,
  created_at: "2026-06-03T00:00:00Z",
};

const server = setupServer(
  http.get("/api/users/me", () => HttpResponse.json(ME_RESPONSE)),
);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
// Pre-seed the walletStore so BalanceHeader renders the balance display (no
// role="status") when the component first mounts synchronously.
beforeEach(() => {
  useWalletStore.setState({ balance: ME_RESPONSE.chip_balance, loading: false, error: null });
});
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderLobby() {
  return render(
    <MemoryRouter>
      <HoldemLobby />
    </MemoryRouter>,
  );
}

describe("HoldemLobby", () => {
  it("renders the table list with blinds + seats once loaded", async () => {
    server.use(http.get("/api/holdem/tables", () => HttpResponse.json([TABLE])));
    renderLobby();
    // loading state first
    expect(screen.getByRole("status")).toBeInTheDocument();
    // then the table appears
    await waitFor(() => expect(screen.getByText("Felt Five")).toBeInTheDocument());
    expect(screen.getByTestId(`holdem-table-row-${TABLE.id}`)).toBeInTheDocument();
    expect(screen.getByText(/2\/6/)).toBeInTheDocument(); // seats_taken/max_seats
    expect(screen.getByTestId(`holdem-join-${TABLE.id}`)).toBeInTheDocument();
  });

  it("renders an error branch when the fetch fails", async () => {
    server.use(http.get("/api/holdem/tables", () => new HttpResponse(null, { status: 500 })));
    renderLobby();
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });

  it("shows the empty state when there are no tables", async () => {
    server.use(http.get("/api/holdem/tables", () => HttpResponse.json([])));
    renderLobby();
    await waitFor(() => expect(screen.getByText(/no tables running/i)).toBeInTheDocument());
  });
});
