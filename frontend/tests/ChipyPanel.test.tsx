/**
 * ChipyPanel.test.tsx — the 4 mandatory Vitest cases from
 * specs/betwise-casino-source.md Step 6 and specs/betwise-casino.md §7.
 *
 * Import path: src/components/ChipyPanel
 * (Cannot find module until T22 lands)
 *
 * MSW is used to mock POST /api/advice/:id as a Server-Sent Events stream
 * so no test hits the real backend.
 */

import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { beforeAll, afterAll, afterEach, describe, it, expect, vi } from "vitest";

// ---- Production import under test ----------------------------------------
// This will throw "Cannot find module" until the implementer creates
// betwise-casino/frontend/src/components/ChipyPanel.tsx
import ChipyPanel from "../src/components/ChipyPanel";

// ---- Types (mirrors backend schemas) -------------------------------------
type Action = "hit" | "stand" | "double" | "split";

interface ChipyPanelProps {
  handId: string;
  legalActions: Action[];
  dealerUpcard: { suit: string; value: string };
  onConfirm: (action: Action) => void;
}

// ---- MSW SSE mock helpers ------------------------------------------------

/**
 * Build a fake SSE ReadableStream that emits text chunks then a final JSON
 * event identical to what the real /api/advice endpoint would send.
 */
function makeFakeSseStream(chunks: string[], finalPayload: object): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(`data: ${chunk}\n\n`));
      }
      const finalLine = `data: ${JSON.stringify(finalPayload)}\n\n`;
      controller.enqueue(encoder.encode(finalLine));
      controller.close();
    },
  });
}

// ---- MSW server ----------------------------------------------------------

const HAND_ID = "hand-test-001";

const FINAL_PAYLOAD = {
  optimal_action: "hit",
  was_correct: true,
  player_accuracy: 0.72,
  current_streak: 3,
  best_streak: 5,
};

const handlers = [
  http.post(`/api/advice/${HAND_ID}`, () => {
    const stream = makeFakeSseStream(
      ["Great move! ", "You chose wisely."],
      FINAL_PAYLOAD,
    );
    return new HttpResponse(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  }),
];

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---- Test helpers --------------------------------------------------------

const defaultProps: ChipyPanelProps = {
  handId: HAND_ID,
  legalActions: ["hit", "stand", "double", "split"],
  dealerUpcard: { suit: "spades", value: "6" },
  onConfirm: vi.fn(),
};

function renderPanel(props: Partial<ChipyPanelProps> = {}) {
  return render(<ChipyPanel {...defaultProps} {...props} />);
}

// ─────────────────────────────────────────────────────────────────────────────
// Criterion T22 / source-spec Step 6:
// "Test that ChipyPanel renders guess buttons (Hit, Stand, Double, Split)"
// ─────────────────────────────────────────────────────────────────────────────
describe("renders guess buttons (Hit, Stand, Double, Split)", () => {
  it("shows all four action buttons when all actions are legal", () => {
    renderPanel();
    expect(screen.getByRole("button", { name: /hit/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /stand/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /double/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /split/i })).toBeInTheDocument();
  });

  it("disables buttons for illegal actions", () => {
    renderPanel({ legalActions: ["hit", "stand"] });
    // Double and split should be present but disabled
    const doubleBtn = screen.getByRole("button", { name: /double/i });
    const splitBtn  = screen.getByRole("button", { name: /split/i });
    expect(doubleBtn).toBeDisabled();
    expect(splitBtn).toBeDisabled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Criterion:
// "Test that clicking a guess calls the advice endpoint with the chosen guess"
// ─────────────────────────────────────────────────────────────────────────────
describe("clicking a guess calls the advice endpoint with the chosen guess", () => {
  it("POSTs player_guess to /api/advice/:handId when a button is clicked", async () => {
    const user = userEvent.setup();
    const requestBodies: unknown[] = [];

    // Override the handler to capture the request body
    server.use(
      http.post(`/api/advice/${HAND_ID}`, async ({ request }) => {
        requestBodies.push(await request.json());
        const stream = makeFakeSseStream(["ok"], FINAL_PAYLOAD);
        return new HttpResponse(stream, {
          headers: { "Content-Type": "text/event-stream" },
        });
      }),
    );

    renderPanel();
    await user.click(screen.getByRole("button", { name: /hit/i }));

    await waitFor(() => expect(requestBodies.length).toBeGreaterThan(0));
    const body = requestBodies[0] as { player_guess: string };
    expect(body.player_guess).toBe("hit");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Criterion:
// "Test that the panel shows loading state while streaming"
// ─────────────────────────────────────────────────────────────────────────────
describe("shows loading state while streaming", () => {
  it("renders a loading indicator after a guess is submitted and before streaming completes", async () => {
    const user = userEvent.setup();

    // Use a slow stream so loading state persists long enough to assert
    let resolveStream!: () => void;
    const slowStream = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        // Enqueue one chunk immediately
        controller.enqueue(encoder.encode("data: thinking...\n\n"));
        // Don't close until the test resolves
        new Promise<void>((res) => { resolveStream = res; }).then(() => {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(FINAL_PAYLOAD)}\n\n`));
          controller.close();
        });
      },
    });

    server.use(
      http.post(`/api/advice/${HAND_ID}`, () =>
        new HttpResponse(slowStream, {
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );

    renderPanel();
    await user.click(screen.getByRole("button", { name: /stand/i }));

    // Loading state must appear synchronously or very quickly after click
    await waitFor(() => {
      // Accept any of: aria-busy, role=status, role=progressbar, or text "loading"
      const loading =
        document.querySelector("[aria-busy='true']") ||
        document.querySelector("[role='status']") ||
        document.querySelector("[role='progressbar']") ||
        screen.queryByText(/loading/i);
      expect(loading).toBeTruthy();
    });

    // Clean up: resolve the stream so no pending async work leaks
    act(() => resolveStream());
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// Criterion:
// "Test that confirm button appears after explanation completes"
// ─────────────────────────────────────────────────────────────────────────────
describe("confirm button appears after explanation completes", () => {
  it("shows a 'Confirm' button once the SSE stream closes", async () => {
    const user = userEvent.setup();

    renderPanel();
    // Confirm button must NOT be present before any interaction
    expect(screen.queryByRole("button", { name: /confirm/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /hit/i }));

    // After stream completes, Confirm button must appear
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /confirm/i })).toBeInTheDocument();
    });
  });

  it("confirm button is labelled with the chosen action", async () => {
    const user = userEvent.setup();

    renderPanel();
    await user.click(screen.getByRole("button", { name: /stand/i }));

    await waitFor(() => {
      // Accept "Confirm Stand", "Confirm stand", "Confirm (stand)", etc.
      const btn = screen.getByRole("button", { name: /confirm/i });
      expect(btn).toBeInTheDocument();
      expect(btn.textContent?.toLowerCase()).toContain("stand");
    });
  });
});
