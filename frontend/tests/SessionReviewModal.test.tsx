/**
 * SessionReviewModal.test.tsx — Hand Review modal Vitest tests.
 *
 * Maps to acceptance criteria AC-F2, AC-F8, and AC-T2.
 * All three tests are expected to FAIL until the implementer creates:
 *   frontend/src/components/SessionReviewModal.tsx
 *
 * MSW pattern mirrors ChipyPanel.test.tsx.
 * Endpoint mocked: GET /api/sessions/:sessionId/review
 */

import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { beforeAll, afterAll, afterEach, describe, it, expect, vi } from "vitest";

// Production import under test — will throw "Cannot find module" until
// the implementer creates frontend/src/components/SessionReviewModal.tsx
import SessionReviewModal from "../src/components/SessionReviewModal";

const SESSION_ID = "session-abc";
const HAND_ID = "hand-abc";

const SUCCESS_BODY = {
  session_id: SESSION_ID,
  hand_id: HAND_ID,
  total_actions: 2,
  optimal_count: 1,
  accuracy: 0.5,
  ev_lost_chips: 200,
  worst_action_id: "action-2",
  actions: [
    {
      id: "action-1",
      hand_id: HAND_ID,
      user_id: "user-1",
      action: "hit",
      player_guess: "hit",
      optimal_action: "hit",
      was_correct: true,
      hand_snapshot: [
        { suit: "hearts", value: "5" },
        { suit: "clubs", value: "3" },
      ],
      dealer_upcard: { suit: "clubs", value: "6" },
      chipy_explanation: null,
      created_at: "2026-05-21T00:00:00Z",
      classification: "best",
      ev_loss_chips: 0,
    },
    {
      id: "action-2",
      hand_id: HAND_ID,
      user_id: "user-1",
      action: "stand",
      player_guess: "stand",
      optimal_action: "hit",
      was_correct: false,
      hand_snapshot: [
        { suit: "hearts", value: "5" },
        { suit: "clubs", value: "3" },
      ],
      dealer_upcard: { suit: "clubs", value: "6" },
      chipy_explanation: "Stand on 8 is never right.",
      created_at: "2026-05-21T00:00:01Z",
      classification: "blunder",
      ev_loss_chips: 200,
    },
  ],
};

const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("SessionReviewModal", () => {
  it("renders a loading state before the fetch completes", () => {
    /**
     * AC-F2, AC-T2 — loading state (aria-busy="true") must appear immediately
     * on mount, before any network response arrives.
     */
    server.use(
      http.get(`/api/sessions/${SESSION_ID}/review`, async () => {
        await new Promise<void>((r) => setTimeout(r, 50));
        return HttpResponse.json(SUCCESS_BODY);
      }),
    );
    render(
      <SessionReviewModal
        sessionId={SESSION_ID}
        handId={HAND_ID}
        onClose={vi.fn()}
      />,
    );
    expect(document.querySelector("[aria-busy='true']")).toBeTruthy();
  });

  it("renders an error state when the fetch fails", async () => {
    /**
     * AC-F2, AC-T2 — error state (role=alert) must appear after a non-200
     * response from the review endpoint.
     */
    server.use(
      http.get(`/api/sessions/${SESSION_ID}/review`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    render(
      <SessionReviewModal
        sessionId={SESSION_ID}
        handId={HAND_ID}
        onClose={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });

  it("renders accuracy and at least one classification chip with the blunder color on success", async () => {
    /**
     * AC-F8, AC-T2 — success state must show accuracy as a percentage string
     * and render the blunder classification chip with text-red-300 class.
     */
    server.use(
      http.get(`/api/sessions/${SESSION_ID}/review`, () =>
        HttpResponse.json(SUCCESS_BODY),
      ),
    );
    render(
      <SessionReviewModal
        sessionId={SESSION_ID}
        handId={HAND_ID}
        onClose={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/50%/)).toBeInTheDocument();
    });
    // At least one chip element must carry the blunder red color class
    const blunderChip = screen.getByText(/blunder/i);
    expect(blunderChip.className).toMatch(/text-red-300/);
  });
});
