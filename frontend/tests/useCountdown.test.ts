/**
 * useCountdown.test.ts — the pure seconds-remaining helper behind the move timer.
 */
import { describe, it, expect } from "vitest";
import { secondsRemaining } from "../src/hooks/useCountdown";

const NOW = Date.parse("2026-06-03T12:00:00Z");

describe("secondsRemaining", () => {
  it("is null when there is no deadline", () => {
    expect(secondsRemaining(null, NOW)).toBeNull();
  });

  it("is the whole seconds until the deadline", () => {
    expect(secondsRemaining("2026-06-03T12:00:30Z", NOW)).toBe(30);
  });

  it("rounds up the partial second so the display never shows 0 early", () => {
    expect(secondsRemaining("2026-06-03T12:00:29.4Z", NOW)).toBe(30);
  });

  it("floors at zero once the deadline has passed", () => {
    expect(secondsRemaining("2026-06-03T11:59:50Z", NOW)).toBe(0);
  });
});
