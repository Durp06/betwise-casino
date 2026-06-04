/**
 * HoldemRulesModal.test.tsx — the Multiplayer Hold'em rules popup renders the
 * key facts and is dismissable four ways (×, "Got it", backdrop, Escape).
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import HoldemRulesModal from "../src/components/HoldemRulesModal";

describe("HoldemRulesModal", () => {
  it("renders as a dialog with the title and key rules", () => {
    render(<HoldemRulesModal onClose={() => {}} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/How to Play Multiplayer Hold'em/i)).toBeInTheDocument();
    expect(screen.getByText(/Cash ring game/i)).toBeInTheDocument();
    expect(screen.getByText(/Straight flush/i)).toBeInTheDocument();
  });

  it("closes via the × button", () => {
    const onClose = vi.fn();
    render(<HoldemRulesModal onClose={onClose} />);
    fireEvent.click(screen.getByLabelText(/close/i));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes via the "Got it" button', () => {
    const onClose = vi.fn();
    render(<HoldemRulesModal onClose={onClose} />);
    fireEvent.click(screen.getByText(/Got it/i));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes when the backdrop is clicked", () => {
    const onClose = vi.fn();
    render(<HoldemRulesModal onClose={onClose} />);
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<HoldemRulesModal onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
