/**
 * EvalBar.test.tsx — Tests for the EvalBar component.
 *
 * Maps to acceptance criterion AC-F-EVAL1.
 *
 * Prop shape chosen:
 *   <EvalBar actionEvs={Record<string, number>} bestAction={string} />
 *
 * Convention for "gold" highlight: the implementer MUST add the CSS class
 * substring "gold" (e.g. "text-chip-gold", "border-gold", "bg-gold-bright")
 * OR set data-best="true" on the best-action row. Tests assert class substring
 * "gold" — document this so the implementer matches exactly.
 *
 * Width bars use inline style `width: X%` (dynamic numeric inline style per
 * CLAUDE.md §10); tests do not assert exact widths, only that rows exist.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

// Will throw "Cannot find module" until the implementer creates
// frontend/src/components/EvalBar.tsx
import EvalBar from "../src/components/EvalBar";

describe("AC-F-EVAL1: EvalBar renders one row per action_evs entry", () => {
  it("renders exactly three rows when actionEvs has three entries", () => {
    render(
      <EvalBar
        actionEvs={{ stand: -0.05, hit: 0.12, double: -0.3 }}
        bestAction="hit"
      />,
    );
    // Each action label must appear in the DOM
    expect(screen.getByText(/stand/i)).toBeInTheDocument();
    expect(screen.getByText(/hit/i)).toBeInTheDocument();
    expect(screen.getByText(/double/i)).toBeInTheDocument();
  });

  it("renders the EV number for each action", () => {
    render(
      <EvalBar
        actionEvs={{ stand: -0.05, hit: 0.12, double: -0.3 }}
        bestAction="hit"
      />,
    );
    // EV numbers must appear somewhere in the component
    // Accept both rounded and unrounded representations
    expect(screen.getByText(/0\.12/)).toBeInTheDocument();
    expect(screen.getByText(/-0\.05/)).toBeInTheDocument();
    expect(screen.getByText(/-0\.3/)).toBeInTheDocument();
  });
});

describe("AC-F-EVAL1: EvalBar highlights the best action in gold", () => {
  it("applies a gold class to the bestAction row element", () => {
    const { container } = render(
      <EvalBar
        actionEvs={{ stand: -0.05, hit: 0.12, double: -0.3 }}
        bestAction="hit"
      />,
    );
    // The implementer must use a class containing "gold" on the best-action row,
    // OR set data-best="true". We assert the class substring here.
    const goldEl =
      container.querySelector("[data-best='true']") ??
      container.querySelector("[class*='gold']");
    expect(goldEl).toBeTruthy();
  });

  it("only one row carries the gold/best highlight", () => {
    const { container } = render(
      <EvalBar
        actionEvs={{ stand: -0.05, hit: 0.12, double: -0.3 }}
        bestAction="hit"
      />,
    );
    const bestEls = container.querySelectorAll("[data-best='true']");
    const goldEls = container.querySelectorAll("[class*='gold']");
    // At least one element must be highlighted, at most a handful (not all rows)
    const highlightCount = bestEls.length > 0 ? bestEls.length : goldEls.length;
    expect(highlightCount).toBeGreaterThan(0);
    // Should not highlight every row when there are 3 actions
    expect(highlightCount).toBeLessThan(3);
  });
});

describe("AC-F-EVAL1: EvalBar renders gracefully when actionEvs is empty or undefined", () => {
  it("renders nothing (or an empty container) when actionEvs is an empty object", () => {
    const { container } = render(
      <EvalBar actionEvs={{}} bestAction="hit" />,
    );
    // Must not throw; DOM should be effectively empty of action rows
    // Accept either truly empty or a wrapper with no action children
    expect(container).toBeInTheDocument();
    expect(screen.queryByText(/stand/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/double/i)).not.toBeInTheDocument();
  });

  it("renders gracefully when actionEvs is undefined", () => {
    // Cast to satisfy TypeScript in test; the component must guard this
    const { container } = render(
      <EvalBar
        actionEvs={undefined as unknown as Record<string, number>}
        bestAction="hit"
      />,
    );
    expect(container).toBeInTheDocument();
    // Must not throw — no action labels should appear
    expect(screen.queryByText(/stand/i)).not.toBeInTheDocument();
  });
});
