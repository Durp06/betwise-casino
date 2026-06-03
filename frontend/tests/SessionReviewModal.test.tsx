/**
 * SessionReviewModal.test.tsx — Hand Review modal Vitest tests.
 *
 * Existing tests map to AC-F2, AC-F8, AC-T2.
 * New tests (appended) map to AC-F-REV1, AC-F-REV2 (BetWise Study).
 *
 * Endpoint mocked: GET /api/sessions/:sessionId/review
 * MSW pattern mirrors ChipyPanel.test.tsx.
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

// ─── Enriched review fixture for AC-F-REV1 / AC-F-REV2 ──────────────────────
//
// action-1: classification "sharp"   — player chose the optimal action AND it's
//           in the Sharp curated set; carries action_evs so EvalBar renders.
// action-2: classification "blunder" — non-best decision with ev_delta > 0 and
//           dealer_bust_pct present, so the what-if line must render.
//
// SessionReview gains optional sharp_count / blunder_count aggregates.

const ENRICHED_BODY = {
  session_id: SESSION_ID,
  hand_id: HAND_ID,
  total_actions: 2,
  optimal_count: 1,
  accuracy: 0.5,
  ev_lost_chips: 150,
  worst_action_id: "action-2",
  sharp_count: 1,
  blunder_count: 1,
  actions: [
    {
      id: "action-1",
      hand_id: HAND_ID,
      user_id: "user-1",
      // Player stood on hard-16 vs 10 — the sharp move
      action: "hit",
      player_guess: "hit",
      optimal_action: "hit",
      was_correct: true,
      hand_snapshot: [
        { suit: "spades", value: "10" },
        { suit: "hearts", value: "6" },
      ],
      dealer_upcard: { suit: "diamonds", value: "10" },
      chipy_explanation: "Hitting 16 vs 10 is the sharp play.",
      created_at: "2026-05-21T00:00:00Z",
      classification: "sharp",
      ev_loss_chips: 0,
      // Enriched fields
      action_evs: { hit: -0.54, stand: -0.54 },
      best_action: "hit",
      best_ev: -0.54,
      ev_delta: 0.0,
      dealer_bust_pct: 0.23,
    },
    {
      id: "action-2",
      hand_id: HAND_ID,
      user_id: "user-1",
      // Player stood — wrong action, non-best
      action: "stand",
      player_guess: "stand",
      optimal_action: "hit",
      was_correct: false,
      hand_snapshot: [
        { suit: "hearts", value: "8" },
        { suit: "clubs", value: "5" },
      ],
      dealer_upcard: { suit: "clubs", value: "6" },
      chipy_explanation: "Stand on 13 vs 6 is a mistake.",
      created_at: "2026-05-21T00:00:01Z",
      classification: "blunder",
      ev_loss_chips: 150,
      // Enriched fields
      action_evs: { hit: 0.03, stand: -0.12, double: 0.07 },
      best_action: "double",
      best_ev: 0.07,
      ev_delta: 0.19,
      dealer_bust_pct: 0.42,
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

// ─── AC-F-REV1: EvalBar per decision + what-if line ──────────────────────────
//
// When actions carry action_evs, the modal must render:
//   1. An EvalBar for each decision (assert an EV number from action_evs appears).
//   2. A what-if line for non-best decisions matching:
//        "You {action}. Best was {best_action} — dealer's {upcard} busts ~{pct}%."
//      (flexible whitespace; assert substring presence).
//
// The ENRICHED_BODY fixture has:
//   action-1: sharp, action_evs present — EvalBar renders -0.54
//   action-2: blunder, best_action="double", dealer_upcard="6", dealer_bust_pct=0.42
//             → what-if line must mention "stand", "double", "6", "42"

describe("AC-F-REV1: SessionReviewModal renders EvalBar per decision and what-if line", () => {
  it("renders an EV number from action_evs when actions carry enriched data", async () => {
    server.use(
      http.get(`/api/sessions/${SESSION_ID}/review`, () =>
        HttpResponse.json(ENRICHED_BODY),
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
      // -0.54 comes from action-1's action_evs; this confirms EvalBar rendered
      expect(screen.getByText(/-0\.54/)).toBeInTheDocument();
    });
  });

  it("renders a what-if line for a non-best decision containing the played action, best action, upcard, and bust pct", async () => {
    server.use(
      http.get(`/api/sessions/${SESSION_ID}/review`, () =>
        HttpResponse.json(ENRICHED_BODY),
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
      // The spec wording: "You {action}. Best was {best_action} — dealer's {upcard} busts ~{pct}%."
      // action-2: action=stand, best_action=double, dealer_upcard.value=6, dealer_bust_pct=0.42 → ~42%
      // Assert substrings independently; allow flexible whitespace/punctuation.
      const bodyText = document.body.textContent ?? "";
      expect(bodyText).toMatch(/stand/i);
      expect(bodyText).toMatch(/double/i);
      // "busts" substring confirms the what-if line exists
      expect(bodyText).toMatch(/busts/i);
      // ~42% confirms the pct is rendered
      expect(bodyText).toMatch(/42/);
    });
  });
});

// ─── AC-F-REV2: Sharp chip vs Best chip are visually distinct ────────────────
//
// For a "sharp" action the chip must render with a gold-class (distinct from
// "best" chip's green class). CLASSIFICATION_CLASS["sharp"] must differ from
// CLASSIFICATION_CLASS["best"].
//
// Convention chosen (implementer must match):
//   CLASSIFICATION_CLASS["sharp"] MUST contain a class substring "gold"
//     e.g. "bg-gold-bright/20 text-chip-gold" or similar.
//   CLASSIFICATION_CLASS["best"]  uses green (existing: "text-green-300").
//
// Tests assert:
//   1. Both "sharp" and "best" text appear in the DOM.
//   2. The sharp chip's className contains "gold" (or differs from green-300).
//   3. The best chip's className contains "green".

describe("AC-F-REV2: sharp chip is visually distinct from best chip", () => {
  it("renders both a sharp chip and a best chip (from enriched fixture with sharp + blunder)", async () => {
    // ENRICHED_BODY has a "sharp" action. We also need a "best" action for comparison.
    // We reuse a variant of ENRICHED_BODY where action-2 is "best" to get both on screen.
    // chipy_explanation is cleared to avoid ambiguous /sharp/i matches in explanation text.
    const mixedBody = {
      ...ENRICHED_BODY,
      actions: [
        { ...ENRICHED_BODY.actions[0], chipy_explanation: null }, // sharp chip only
        {
          ...ENRICHED_BODY.actions[1],
          classification: "best",
          ev_loss_chips: 0,
          chipy_explanation: null,
        },
      ],
    };

    server.use(
      http.get(`/api/sessions/${SESSION_ID}/review`, () =>
        HttpResponse.json(mixedBody),
      ),
    );
    render(
      <SessionReviewModal
        sessionId={SESSION_ID}
        handId={HAND_ID}
        onClose={vi.fn()}
      />,
    );
    // The ClassificationChip renders the classification string uppercased/lowercase
    // but the text content matches /sharp/i on the chip span element.
    // We use getAllByText and check at least one is a <span> chip (not a <p>).
    await waitFor(() => {
      const sharpEls = screen.getAllByText(/^sharp$/i);
      const bestEls  = screen.getAllByText(/^best$/i);
      expect(sharpEls.length).toBeGreaterThan(0);
      expect(bestEls.length).toBeGreaterThan(0);
    });
  });

  it("sharp chip uses a gold class and best chip uses a green class", async () => {
    const mixedBody = {
      ...ENRICHED_BODY,
      actions: [
        { ...ENRICHED_BODY.actions[0], chipy_explanation: null },
        {
          ...ENRICHED_BODY.actions[1],
          classification: "best",
          ev_loss_chips: 0,
          chipy_explanation: null,
        },
      ],
    };

    server.use(
      http.get(`/api/sessions/${SESSION_ID}/review`, () =>
        HttpResponse.json(mixedBody),
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
      // Find the chip <span> elements by exact text (classification chips render
      // the classification string as their only text content).
      const sharpChips = screen.getAllByText(/^sharp$/i);
      const bestChips  = screen.getAllByText(/^best$/i);

      // At least one of each must be present
      expect(sharpChips.length).toBeGreaterThan(0);
      expect(bestChips.length).toBeGreaterThan(0);

      // Take the first match for each (the chip span)
      const sharpChip = sharpChips[0];
      const bestChip  = bestChips[0];

      // sharp chip must carry a gold class (not the same green as "best")
      expect(sharpChip.className).toMatch(/gold/i);
      // best chip must carry a green class (existing behavior)
      expect(bestChip.className).toMatch(/green/i);
      // They must differ
      expect(sharpChip.className).not.toBe(bestChip.className);
    });
  });
});
