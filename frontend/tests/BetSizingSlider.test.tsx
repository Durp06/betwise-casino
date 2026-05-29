/**
 * BetSizingSlider.test.tsx — preset clicks notify the parent.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import BetSizingSlider from "../src/components/BetSizingSlider";

describe("BetSizingSlider", () => {
  it("calls onChange with the all-in amount when 'all-in' clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <BetSizingSlider
        minRaise={20}
        maxRaise={1500}
        potSize={120}
        initialValue={40}
        onChange={onChange}
      />,
    );
    await user.click(screen.getByTestId("bet-preset-all-in"));
    expect(onChange).toHaveBeenLastCalledWith(1500);
  });

  it("clamps presets to [minRaise, maxRaise]", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <BetSizingSlider
        minRaise={100}
        maxRaise={500}
        potSize={40}
        initialValue={100}
        onChange={onChange}
      />,
    );
    // ¼ pot of 40 is 10, below minRaise (100) — should clamp to 100.
    await user.click(screen.getByTestId("bet-preset-¼ pot"));
    expect(onChange).toHaveBeenLastCalledWith(100);
  });

  it("shows min and max labels", () => {
    render(
      <BetSizingSlider
        minRaise={20}
        maxRaise={200}
        potSize={50}
        initialValue={20}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/min 20/)).toBeInTheDocument();
    expect(screen.getByText(/max 200/)).toBeInTheDocument();
  });
});
