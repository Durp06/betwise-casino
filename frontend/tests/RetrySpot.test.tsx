/**
 * RetrySpot.test.tsx — Tests for the RetrySpot drill component.
 *
 * Maps to acceptance criterion AC-F-RETRY1.
 *
 * Prop shape chosen:
 *   <RetrySpot
 *     hand={Card[]}
 *     dealerUpcard={Card}
 *     onClose?: () => void
 *   />
 *
 * MSW mocks POST /api/practice/grade (wildcard host so Vitest intercepts).
 * The component must:
 *   1. Render action buttons (hit/stand/double at minimum).
 *   2. Show a loading indicator after click, before resolve.
 *   3. Render the returned verdict (classification + EV / explanation) after resolve.
 *   4. Show role="alert" on a 500 error response.
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
  vi,
} from "vitest";

// Will throw "Cannot find module" until the implementer creates
// frontend/src/components/RetrySpot.tsx
import RetrySpot from "../src/components/RetrySpot";

// ─── Shared MSW server ────────────────────────────────────────────────────────

const PRACTICE_GRADE_OK = {
  optimal_action: "hit",
  action_evs: { hit: 0.1, stand: -0.2 },
  best_ev: 0.1,
  ev_delta: 0.0,
  classification: "best",
  dealer_bust_pct: 0.23,
  explanation: "Hitting is best here.",
};

const server = setupServer(
  http.post("*/api/practice/grade", () =>
    HttpResponse.json(PRACTICE_GRADE_OK),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ─── Shared props ─────────────────────────────────────────────────────────────

const HAND = [
  { suit: "hearts" as const, value: "10" as const },
  { suit: "spades" as const, value: "6" as const },
];
const DEALER_UPCARD = { suit: "diamonds" as const, value: "10" as const };

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("AC-F-RETRY1: RetrySpot renders action buttons for the spot", () => {
  it("shows at least hit and stand buttons on mount", () => {
    render(
      <RetrySpot hand={HAND} dealerUpcard={DEALER_UPCARD} onClose={vi.fn()} />,
    );
    expect(
      screen.getByRole("button", { name: /hit/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /stand/i }),
    ).toBeInTheDocument();
  });

  it("shows a double button (hand has 2 cards so doubling is legal)", () => {
    render(
      <RetrySpot hand={HAND} dealerUpcard={DEALER_UPCARD} onClose={vi.fn()} />,
    );
    expect(
      screen.getByRole("button", { name: /double/i }),
    ).toBeInTheDocument();
  });
});

describe("AC-F-RETRY1: clicking an action fires the POST and renders the verdict", () => {
  it("calls POST /api/practice/grade and renders the classification after resolve", async () => {
    const user = userEvent.setup();
    render(
      <RetrySpot hand={HAND} dealerUpcard={DEALER_UPCARD} onClose={vi.fn()} />,
    );

    await user.click(screen.getByRole("button", { name: /hit/i }));

    await waitFor(() => {
      // The verdict classification must appear in the DOM
      expect(screen.getByText(/best/i)).toBeInTheDocument();
    });
  });

  it("renders the explanation text returned from the server after resolve", async () => {
    const user = userEvent.setup();
    render(
      <RetrySpot hand={HAND} dealerUpcard={DEALER_UPCARD} onClose={vi.fn()} />,
    );

    await user.click(screen.getByRole("button", { name: /stand/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/Hitting is best here/i),
      ).toBeInTheDocument();
    });
  });

  it("renders an EV number from action_evs after resolve", async () => {
    const user = userEvent.setup();
    render(
      <RetrySpot hand={HAND} dealerUpcard={DEALER_UPCARD} onClose={vi.fn()} />,
    );

    await user.click(screen.getByRole("button", { name: /hit/i }));

    await waitFor(() => {
      // 0.1 or -0.2 must appear somewhere (EvalBar or verdict summary)
      const hasEv =
        screen.queryByText(/0\.1/) !== null ||
        screen.queryByText(/-0\.2/) !== null;
      expect(hasEv).toBe(true);
    });
  });
});

describe("AC-F-RETRY1: RetrySpot shows loading while request is in flight", () => {
  it("shows a loading indicator after click before the response resolves", async () => {
    // Slow handler — never resolves during the assertion window
    let resolveHandler!: () => void;
    server.use(
      http.post("*/api/practice/grade", () =>
        new Promise<Response>((resolve) => {
          resolveHandler = () =>
            resolve(HttpResponse.json(PRACTICE_GRADE_OK) as Response);
        }),
      ),
    );

    const user = userEvent.setup();
    render(
      <RetrySpot hand={HAND} dealerUpcard={DEALER_UPCARD} onClose={vi.fn()} />,
    );

    await user.click(screen.getByRole("button", { name: /hit/i }));

    // Loading indicator must appear while the request is pending
    await waitFor(() => {
      const loading =
        document.querySelector("[aria-busy='true']") ??
        document.querySelector("[role='status']") ??
        screen.queryByText(/loading/i) ??
        screen.queryByText(/\.\.\./);
      expect(loading).toBeTruthy();
    });

    // Resolve so no async leak
    resolveHandler();
  });
});

describe("AC-F-RETRY1: RetrySpot shows an error state on server failure", () => {
  it("renders role=alert when POST /api/practice/grade returns 500", async () => {
    server.use(
      http.post("*/api/practice/grade", () =>
        HttpResponse.json({ detail: "server error" }, { status: 500 }),
      ),
    );

    const user = userEvent.setup();
    render(
      <RetrySpot hand={HAND} dealerUpcard={DEALER_UPCARD} onClose={vi.fn()} />,
    );

    await user.click(screen.getByRole("button", { name: /hit/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});
