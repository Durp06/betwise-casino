/**
 * HandHistory.test.tsx — Tests for the HandHistory page.
 *
 * Maps to acceptance criterion AC-F-HIST1.
 *
 * Strategy for current-user resolution:
 *   HandHistory must know the current user's id to call getUserHands(userId).
 *   Profile.tsx obtains it from supabase.auth.getSession() via useSession().
 *   Rather than mock Supabase (fragile under jsdom), HandHistory should call
 *   GET /api/users/me first, then GET /api/users/:id/hands.
 *   Tests mock BOTH endpoints. If the implementer wires it differently, they
 *   must update the MSW handlers here to match — document the choice.
 *
 * MSW server: onUnhandledRequest "error" to catch missing handlers early.
 *
 * Minimal SessionReview stub is also mocked so that clicking a hand to open
 * the review modal does not 404.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import {
  beforeAll,
  afterAll,
  afterEach,
  describe,
  it,
  expect,
} from "vitest";

// Will throw "Cannot find module" until the implementer creates
// frontend/src/pages/HandHistory.tsx
import HandHistory from "../src/pages/HandHistory";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const ME = {
  id: "u1",
  username: "testplayer",
  chip_balance: 100000,
  total_hands: 2,
  correct_decisions: 1,
  accuracy: 0.5,
  current_streak: 1,
  best_streak: 3,
  created_at: "2026-05-01T00:00:00Z",
};

// Two hands newest-first (most recent created_at first)
const HANDS = [
  {
    id: "hand-2",
    session_id: "session-2",
    user_id: "u1",
    cards: [
      { suit: "hearts", value: "A" },
      { suit: "clubs", value: "K" },
    ],
    bet: 1000,
    status: "finished",
    outcome: "blackjack",
    payout: 2500,
  },
  {
    id: "hand-1",
    session_id: "session-1",
    user_id: "u1",
    cards: [
      { suit: "spades", value: "7" },
      { suit: "diamonds", value: "6" },
    ],
    bet: 500,
    status: "finished",
    outcome: "loss",
    payout: 0,
  },
];

const MINIMAL_REVIEW = {
  session_id: "session-2",
  hand_id: "hand-2",
  total_actions: 0,
  optimal_count: 0,
  accuracy: 0,
  ev_lost_chips: 0,
  worst_action_id: null,
  actions: [],
};

// ─── MSW server ───────────────────────────────────────────────────────────────

const server = setupServer(
  http.get("*/api/users/me", () => HttpResponse.json(ME)),
  http.get("*/api/users/:id/hands", () => HttpResponse.json(HANDS)),
  // Stub for the session review opened when a hand is clicked
  http.get("*/api/sessions/:sessionId/review", () =>
    HttpResponse.json(MINIMAL_REVIEW),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("AC-F-HIST1: HandHistory shows a loading state initially", () => {
  it("renders role=status/aria-busy before data arrives", () => {
    // Delay the /me response so loading state persists
    server.use(
      http.get("*/api/users/me", async () => {
        await new Promise<void>((r) => setTimeout(r, 50));
        return HttpResponse.json(ME);
      }),
    );

    render(<HandHistory />);

    const loading =
      document.querySelector("[aria-busy='true']") ??
      document.querySelector("[role='status']");
    expect(loading).toBeTruthy();
  });
});

describe("AC-F-HIST1: HandHistory renders the list of hands on success", () => {
  it("renders one row per hand returned", async () => {
    render(<HandHistory />);

    await waitFor(() => {
      // Both outcomes must appear somewhere in the DOM
      expect(screen.getByText(/blackjack/i)).toBeInTheDocument();
      expect(screen.getByText(/loss/i)).toBeInTheDocument();
    });
  });

  it("renders at least one hand's bet amount", async () => {
    render(<HandHistory />);

    await waitFor(() => {
      // formatMoney shows clean whole dollars: bet=1000 → "$10", bet=500 → "$5"
      // (cents are only shown when an amount is fractional, e.g. a 3:2 payout).
      const hasBet =
        screen.queryByText(/\$10\b/) !== null ||
        screen.queryByText(/\$5\b/) !== null;
      expect(hasBet).toBe(true);
    });
  });
});

describe("AC-F-HIST1: HandHistory shows an error state when hands fetch fails", () => {
  it("renders role=alert when GET /api/users/:id/hands returns 500", async () => {
    server.use(
      http.get("*/api/users/:id/hands", () =>
        HttpResponse.json({ detail: "db error" }, { status: 500 }),
      ),
    );

    render(<HandHistory />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("renders role=alert when GET /api/users/me returns 500", async () => {
    server.use(
      http.get("*/api/users/me", () =>
        HttpResponse.json({ detail: "unauthorized" }, { status: 500 }),
      ),
    );

    render(<HandHistory />);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});

describe("AC-F-HIST1: HandHistory shows empty state when no hands", () => {
  it("renders an empty-state message when hands array is empty", async () => {
    server.use(
      http.get("*/api/users/:id/hands", () => HttpResponse.json([])),
    );

    render(<HandHistory />);

    await waitFor(() => {
      // Any text conveying emptiness; implementer can choose the exact wording
      const empty =
        screen.queryByText(/no hands/i) ??
        screen.queryByText(/nothing here/i) ??
        screen.queryByText(/play a hand/i) ??
        screen.queryByText(/no history/i) ??
        screen.queryByText(/yet/i);
      expect(empty).toBeTruthy();
    });
  });
});

describe("AC-F-HIST1: clicking a hand opens SessionReviewModal", () => {
  it("mounts the Hand Review modal when a hand row is clicked", async () => {
    const user = userEvent.setup();
    render(<HandHistory />);

    // Wait for the list to load
    await waitFor(() => {
      expect(screen.getByText(/blackjack/i)).toBeInTheDocument();
    });

    // Click the first hand row — implementer decides what is the clickable element
    // We find the first element containing "blackjack" and click its closest row/button
    const firstHandEl = screen.getByText(/blackjack/i);
    await user.click(firstHandEl);

    // SessionReviewModal renders a dialog with aria-label="Hand Review"
    await waitFor(() => {
      expect(
        screen.getByRole("dialog", { name: /hand review/i }),
      ).toBeInTheDocument();
    });
  });
});
