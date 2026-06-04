/**
 * TimeCardControl.test.tsx — the Hold'em time-card "+15s" control.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import TimeCardControl from "../src/components/TimeCardControl";

describe("TimeCardControl", () => {
  it("shows the remaining count out of 5", () => {
    render(<TimeCardControl remaining={3} onUse={() => {}} />);
    expect(screen.getByTestId("time-card-control")).toHaveTextContent("3/5");
  });

  it("calls onUse when the +15s button is clicked", () => {
    const onUse = vi.fn();
    render(<TimeCardControl remaining={2} onUse={onUse} />);
    fireEvent.click(screen.getByTestId("time-card-use"));
    expect(onUse).toHaveBeenCalledTimes(1);
  });

  it("disables the button when no cards remain", () => {
    render(<TimeCardControl remaining={0} onUse={() => {}} />);
    expect(screen.getByTestId("time-card-use")).toBeDisabled();
  });

  it("disables the button while a use is in flight", () => {
    render(<TimeCardControl remaining={5} onUse={() => {}} busy />);
    expect(screen.getByTestId("time-card-use")).toBeDisabled();
  });
});
