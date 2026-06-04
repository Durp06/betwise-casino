/**
 * MoveTimer.test.tsx — the per-seat countdown badge.
 */
import { render, screen, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import MoveTimer from "../src/components/MoveTimer";

describe("MoveTimer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-03T12:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders nothing when there is no deadline", () => {
    const { container } = render(<MoveTimer deadlineAt={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the seconds remaining", () => {
    const deadline = new Date("2026-06-03T12:00:20Z").toISOString();
    render(<MoveTimer deadlineAt={deadline} />);
    expect(screen.getByTestId("move-timer")).toHaveTextContent("20s");
  });

  it("ticks down as time passes", () => {
    const deadline = new Date("2026-06-03T12:00:20Z").toISOString();
    render(<MoveTimer deadlineAt={deadline} />);
    expect(screen.getByTestId("move-timer")).toHaveTextContent("20s");
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.getByTestId("move-timer")).toHaveTextContent("15s");
  });

  it("turns urgent (red) under 5 seconds left", () => {
    const deadline = new Date("2026-06-03T12:00:03Z").toISOString();
    render(<MoveTimer deadlineAt={deadline} />);
    expect(screen.getByTestId("move-timer").className).toContain("text-action-hit");
  });

  it("clears its interval on unmount (StrictMode-safe cleanup)", () => {
    const clearSpy = vi.spyOn(globalThis, "clearInterval");
    const deadline = new Date("2026-06-03T12:00:20Z").toISOString();
    const { unmount } = render(<MoveTimer deadlineAt={deadline} />);
    unmount();
    expect(clearSpy).toHaveBeenCalled();
    clearSpy.mockRestore();
  });

  it("clears the old interval when the deadline changes", () => {
    const clearSpy = vi.spyOn(globalThis, "clearInterval");
    const { rerender } = render(
      <MoveTimer deadlineAt={new Date("2026-06-03T12:00:20Z").toISOString()} />,
    );
    rerender(<MoveTimer deadlineAt={new Date("2026-06-03T12:00:40Z").toISOString()} />);
    expect(clearSpy).toHaveBeenCalled();
    clearSpy.mockRestore();
  });
});
