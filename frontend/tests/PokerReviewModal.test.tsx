/**
 * PokerReviewModal.test.tsx — Vitest tests for the shared poker review modal.
 *
 * Mirrors the ChipyPanel.test.tsx setupServer + MSW pattern. Mocks the four
 * compute-on-read review endpoints:
 *   GET /api/holdem/hands/:id/review        → HandReview
 *   GET /api/holdem/tables/:id/review       → GameReview
 *   GET /api/poker/hands/:id/review         → HandReview
 *   GET /api/poker/tournaments/:id/review   → GameReview
 *
 * Covers (per spec ACs):
 *   - Hand Review renders a verdict chip + your-action-vs-recommended + ev_loss
 *     for each action.
 *   - Loading and error branches both render.
 *   - Game Review list renders rows; clicking a row requests that hand's review.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { beforeAll, afterAll, afterEach, describe, it, expect, vi } from "vitest";

import PokerReviewModal from "../src/components/PokerReviewModal";

const HAND_ID = "hand-001";
const TABLE_ID = "tbl-001";
const TOURNAMENT_ID = "tourn-001";

// ─── Fixtures matching the LOCKED HandReview / GameReview contract ───────────

const HAND_REVIEW = {
  hand_id: HAND_ID,
  game: "holdem",
  your_hole: [
    { suit: "hearts", value: "A" },
    { suit: "spades", value: "K" },
  ],
  board: [
    { suit: "clubs", value: "2" },
    { suit: "diamonds", value: "7" },
    { suit: "hearts", value: "9" },
  ],
  graded_count: 2,
  accuracy: 0.5,
  ev_lost_bb: 1.75,
  worst_action_index: 1,
  actions: [
    {
      action_index: 0,
      street: "preflop",
      action: "raise",
      amount_bb: 3.0,
      verdict: "best",
      confidence_tier: "DETERMINISTIC",
      recommended_action: "raise",
      equity: 0.62,
      required_equity: 0.33,
      ev_loss_bb: 0.0,
      explanation: "Opening AKs from the button is standard.",
    },
    {
      action_index: 1,
      street: "flop",
      action: "call",
      amount_bb: 4.0,
      verdict: "blunder",
      confidence_tier: "DETERMINISTIC",
      recommended_action: "fold",
      equity: 0.18,
      required_equity: 0.4,
      ev_loss_bb: 1.75,
      explanation: "Calling with two overcards and no draw burns chips.",
    },
  ],
};

const GAME_REVIEW = {
  scope: "table_visit",
  game: "holdem",
  overall_accuracy: 0.6,
  total_ev_lost_bb: 3.25,
  graded_count: 5,
  hands: [
    {
      hand_id: "hand-aaa",
      accuracy: 0.8,
      ev_lost_bb: 0.5,
      graded_count: 2,
      worst_verdict: "inaccuracy",
    },
    {
      hand_id: "hand-bbb",
      accuracy: 0.4,
      ev_lost_bb: 2.75,
      graded_count: 3,
      worst_verdict: "blunder",
    },
  ],
};

// ─── MSW server ──────────────────────────────────────────────────────────────

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ─── Hand Review ───────────────────────────────────────────────────────────

describe("PokerReviewModal — Hand Review", () => {
  it("renders a verdict chip, your-action-vs-recommended, and ev_loss for each action", async () => {
    server.use(
      http.get(`/api/holdem/hands/${HAND_ID}/review`, () =>
        HttpResponse.json(HAND_REVIEW),
      ),
    );
    render(
      <PokerReviewModal mode="hand" game="holdem" handId={HAND_ID} onClose={vi.fn()} />,
    );

    await waitFor(() => {
      // One row per caller action.
      const rows = screen.getAllByTestId("poker-review-action");
      expect(rows.length).toBe(2);
    });

    // Verdict chips: a "best" chip (green) and a "blunder" chip (red).
    const bestChip = screen.getByText(/^best$/i);
    const blunderChip = screen.getByText(/^blunder$/i);
    expect(bestChip.className).toMatch(/green/);
    expect(blunderChip.className).toMatch(/red/);

    // Your action vs recommended for the blunder action: call / fold.
    const body = document.body.textContent ?? "";
    expect(body).toMatch(/call/i);
    expect(body).toMatch(/fold/i);

    // ev_loss for the blunder action is rendered (1.75 bb).
    const evLoss = screen.getAllByTestId("poker-review-evloss");
    expect(evLoss.length).toBeGreaterThan(0);
    expect(evLoss[0].textContent).toMatch(/1\.75/);

    // Accuracy header (0.5 → 50%).
    expect(screen.getByText(/50%/)).toBeInTheDocument();
  });

  it("renders a loading state before the fetch completes", () => {
    server.use(
      http.get(`/api/holdem/hands/${HAND_ID}/review`, async () => {
        await new Promise<void>((r) => setTimeout(r, 50));
        return HttpResponse.json(HAND_REVIEW);
      }),
    );
    render(
      <PokerReviewModal mode="hand" game="holdem" handId={HAND_ID} onClose={vi.fn()} />,
    );
    expect(document.querySelector("[aria-busy='true']")).toBeTruthy();
  });

  it("renders an error state when the fetch fails", async () => {
    server.use(
      http.get(`/api/holdem/hands/${HAND_ID}/review`, () =>
        HttpResponse.json({ detail: "not a participant" }, { status: 403 }),
      ),
    );
    render(
      <PokerReviewModal mode="hand" game="holdem" handId={HAND_ID} onClose={vi.fn()} />,
    );
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getByRole("alert").textContent).toMatch(/not a participant/i);
  });

  it("routes solo poker hand reviews to the /api/poker endpoint", async () => {
    let hit = false;
    server.use(
      http.get(`/api/poker/hands/${HAND_ID}/review`, () => {
        hit = true;
        return HttpResponse.json({ ...HAND_REVIEW, game: "poker" });
      }),
    );
    render(
      <PokerReviewModal mode="hand" game="poker" handId={HAND_ID} onClose={vi.fn()} />,
    );
    await waitFor(() => expect(hit).toBe(true));
  });
});

// ─── Game Review ─────────────────────────────────────────────────────────────

describe("PokerReviewModal — Game Review", () => {
  it("renders summary + one row per hand, and clicking a row requests that hand's review", async () => {
    const requestedHandIds: string[] = [];
    server.use(
      http.get(`/api/holdem/tables/${TABLE_ID}/review`, () =>
        HttpResponse.json(GAME_REVIEW),
      ),
      http.get("/api/holdem/hands/:handId/review", ({ params }) => {
        requestedHandIds.push(params.handId as string);
        return HttpResponse.json({ ...HAND_REVIEW, hand_id: params.handId });
      }),
    );

    render(
      <PokerReviewModal mode="game" game="holdem" gameId={TABLE_ID} onClose={vi.fn()} />,
    );

    // Summary: overall accuracy 0.6 → 60%.
    await waitFor(() => {
      expect(screen.getByText(/60%/)).toBeInTheDocument();
    });

    // Two hand rows.
    const rows = await screen.findAllByTestId("poker-review-hand-row");
    expect(rows.length).toBe(2);

    // Clicking the first row fetches that hand's Hand Review.
    const user = userEvent.setup();
    await user.click(rows[0]);

    await waitFor(() => {
      expect(requestedHandIds).toContain("hand-aaa");
    });

    // The drilled Hand Review now renders its action rows.
    await waitFor(() => {
      expect(screen.getAllByTestId("poker-review-action").length).toBeGreaterThan(0);
    });
  });

  it("renders a loading state for the game review before the fetch completes", () => {
    server.use(
      http.get(`/api/poker/tournaments/${TOURNAMENT_ID}/review`, async () => {
        await new Promise<void>((r) => setTimeout(r, 50));
        return HttpResponse.json({ ...GAME_REVIEW, scope: "tournament", game: "poker" });
      }),
    );
    render(
      <PokerReviewModal
        mode="game"
        game="poker"
        gameId={TOURNAMENT_ID}
        onClose={vi.fn()}
      />,
    );
    expect(document.querySelector("[aria-busy='true']")).toBeTruthy();
  });

  it("renders an error state when the game review fetch fails", async () => {
    server.use(
      http.get(`/api/poker/tournaments/${TOURNAMENT_ID}/review`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    render(
      <PokerReviewModal
        mode="game"
        game="poker"
        gameId={TOURNAMENT_ID}
        onClose={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});
