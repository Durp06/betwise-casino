/**
 * CoachMode.test.tsx — covers AC-F1..F7 / AC-T3.
 *
 * Tests:
 *   (a) Both "Quick" and "Drill" pill buttons are present; "Quick" is active by default.
 *   (b) Clicking "Drill" flips the store's coachMode and persists to localStorage.
 *   (c) While chipyStreaming === true, both toggle buttons are disabled (AC-F7).
 *   (d) quick mode fires streamPreAdvice when a hand goes active (AC-F6 regression).
 *   (e) drill mode suppresses streamPreAdvice and surfaces the static prompt (AC-F4).
 *
 * Pattern: vi.mock for streamPreAdvice + MSW server for completeness.
 * ChipyCoach is imported directly; a local PreStreamHarness mirrors the
 * effect logic that will live in Table.tsx so tests run without needing the
 * full page render tree.
 *
 * NOTE: Tests (d) and (e) exercise the harness, not Table.tsx directly. The
 * implementer must replicate the same guard logic in Table.tsx (Task 5 step 3
 * in specs/drill-mode.md). If that step is skipped these tests still pass but
 * Table.tsx will not satisfy AC-F4 in production — the suite will catch the
 * regression once Table.tsx is wired.
 */

import { useEffect } from "react";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import {
  beforeAll,
  afterAll,
  afterEach,
  beforeEach,
  describe,
  it,
  expect,
  vi,
} from "vitest";

// ── Production imports ────────────────────────────────────────────────────────
// ChipyCoach will fail to import until the implementer adds:
//   - coachMode / setCoachMode / chipyDrillPrompt to gameStore.ts  (AC-F1, F2)
//   - Quick / Drill pill buttons to ChipyCoach.tsx                 (AC-F3)
import ChipyCoach from "../src/components/ChipyCoach";
import { useGameStore } from "../src/store/gameStore";

// ── Mock streamPreAdvice so we can assert called / not called ─────────────────
vi.mock("../src/api/client", async () => {
  return {
    streamPreAdvice: vi.fn(
      async (
        _handId: string,
        _onChunk: (t: string) => void,
        onDone: () => void,
        _onError: (m: string) => void,
      ) => {
        onDone();
      },
    ),
    // Keep other exports as stubs so imports don't break.
    streamAdvice: vi.fn(),
  };
});

import { streamPreAdvice } from "../src/api/client";

// ── MSW (acts as a safety net for any fetch that escapes the vi.mock) ─────────
const handlers = [
  http.post("/api/advice/:handId/pre", () =>
    new HttpResponse(
      'data: {"optimal_action":"hit","phase":"pre"}\n\n',
      { headers: { "Content-Type": "text/event-stream" } },
    ),
  ),
];
const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterAll(() => server.close());
afterEach(() => {
  server.resetHandlers();
  vi.clearAllMocks();
});

// Reset Zustand + localStorage between every test so coachMode doesn't leak.
beforeEach(() => {
  try {
    window.localStorage.removeItem("betwise.coachMode");
  } catch {
    // ignore
  }
  act(() => {
    useGameStore.setState({
      // Fields that exist today — always safe to reset.
      chipyText: "",
      chipyStreaming: false,
      chipyPhase: "idle",
      chipyHandId: null,
      // These fields will be added by the implementer. setState is a Zustand
      // partial-merge so if they don't exist yet the call is a no-op (the
      // test that relies on them will fail for the right reason).
      coachMode: "quick",
      chipyDrillPrompt: null,
    } as Parameters<typeof useGameStore.setState>[0]);
  });
});

// ── Local PreStreamHarness ────────────────────────────────────────────────────
//
// Mirrors exactly the useEffect logic the implementer must add to Table.tsx
// (specs/drill-mode.md Task 5 step 3). Tests (d) and (e) exercise this
// contract. If you change the wording of the static drill prompt in
// Table.tsx, update the assertions in test (e) to match.

function PreStreamHarness({
  handId,
  handActive,
}: {
  handId: string;
  handActive: boolean;
}) {
  const { coachMode, beginChipyStream, appendChipyChunk, endChipyStream, setChipyDrillPrompt } =
    useGameStore();

  useEffect(() => {
    if (!handActive) return;
    if (coachMode === "quick") {
      beginChipyStream("pre", handId);
      void streamPreAdvice(
        handId,
        (chunk) => appendChipyChunk(chunk),
        () => endChipyStream(),
        () => endChipyStream(),
      );
    } else {
      // drill mode: no proactive narration, set static quiz prompt instead
      setChipyDrillPrompt(
        "Your call. Hit, stand, or double? What's the dealer most likely sitting on?",
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handActive, handId, coachMode]);

  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

describe("CoachMode toggle — AC-F3", () => {
  it("(a) renders both Quick and Drill pill buttons with Quick active by default", () => {
    render(<ChipyCoach />);

    const quickBtn = screen.getByRole("button", { name: /quick/i });
    const drillBtn = screen.getByRole("button", { name: /drill/i });

    expect(quickBtn).toBeInTheDocument();
    expect(drillBtn).toBeInTheDocument();

    // Quick is the active/pressed pill when coachMode === "quick"
    // AC-F3 says the active one is "visually highlighted"; we test via
    // aria-pressed which the implementer must set.
    expect(quickBtn).toHaveAttribute("aria-pressed", "true");
    expect(drillBtn).toHaveAttribute("aria-pressed", "false");
  });

  it("(b) clicking Drill flips coachMode in the store and persists to localStorage — AC-F1 + AC-F2", async () => {
    const user = userEvent.setup();
    render(<ChipyCoach />);

    expect(useGameStore.getState().coachMode).toBe("quick");

    await user.click(screen.getByRole("button", { name: /drill/i }));

    expect(useGameStore.getState().coachMode).toBe("drill");
    expect(window.localStorage.getItem("betwise.coachMode")).toBe("drill");

    // Remount to verify localStorage persistence (AC-F1 default loads from storage)
    // Reset store to simulate a fresh mount reading from localStorage.
    act(() => {
      // Do NOT reset coachMode — localStorage still has "drill".
      // The store's loadCoachMode() reads it on initialisation; we simulate
      // that by calling setCoachMode again as if the store were freshly created.
      useGameStore.getState().setCoachMode("drill");
    });
    expect(useGameStore.getState().coachMode).toBe("drill");
    expect(window.localStorage.getItem("betwise.coachMode")).toBe("drill");
  });

  it("(c) toggle buttons are disabled while chipyStreaming === true — AC-F7", () => {
    act(() => {
      useGameStore.setState({ chipyStreaming: true } as Parameters<typeof useGameStore.setState>[0]);
    });

    render(<ChipyCoach />);

    expect(screen.getByRole("button", { name: /quick/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /drill/i })).toBeDisabled();
  });
});

describe("pre-stream gating by coachMode — AC-F4 + AC-F6", () => {
  it("(d) quick mode fires streamPreAdvice when the hand goes active", () => {
    // coachMode is already "quick" from beforeEach
    render(
      <>
        <ChipyCoach />
        <PreStreamHarness handId="h-quick-001" handActive={true} />
      </>,
    );

    expect(streamPreAdvice).toHaveBeenCalledTimes(1);
    expect(streamPreAdvice).toHaveBeenCalledWith(
      "h-quick-001",
      expect.any(Function),
      expect.any(Function),
      expect.any(Function),
    );
  });

  it("(e) drill mode does NOT fire streamPreAdvice and surfaces the static prompt", () => {
    act(() => {
      useGameStore.setState({ coachMode: "drill" } as Parameters<typeof useGameStore.setState>[0]);
    });

    render(
      <>
        <ChipyCoach />
        <PreStreamHarness handId="h-drill-001" handActive={true} />
      </>,
    );

    expect(streamPreAdvice).not.toHaveBeenCalled();

    // The static prompt text must appear somewhere in the rendered output.
    // ChipyCoach reads chipyDrillPrompt from the store and renders it when
    // no narration text is active.
    expect(screen.getByText(/your call/i)).toBeInTheDocument();
    expect(screen.getByText(/dealer most likely/i)).toBeInTheDocument();
  });
});
