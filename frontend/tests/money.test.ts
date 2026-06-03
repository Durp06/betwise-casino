import { describe, it, expect } from "vitest";
import { formatMoney } from "../src/utils/money";

describe("formatMoney — dollars, not cents", () => {
  it("renders whole dollars with no decimals", () => {
    expect(formatMoney(100000)).toBe("$1,000");
    expect(formatMoney(500)).toBe("$5");
    expect(formatMoney(2500)).toBe("$25");
    expect(formatMoney(0)).toBe("$0");
  });

  it("groups thousands with commas", () => {
    expect(formatMoney(1234500)).toBe("$12,345");
    expect(formatMoney(5000000)).toBe("$50,000");
  });

  it("shows cents only when the amount is fractional (e.g. a 3:2 blackjack payout)", () => {
    expect(formatMoney(750)).toBe("$7.50");
    expect(formatMoney(100050)).toBe("$1,000.50");
  });
});
