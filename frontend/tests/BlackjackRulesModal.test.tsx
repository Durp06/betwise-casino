/**
 * BlackjackRulesModal.test.tsx — the rules popup renders the key facts and is
 * dismissable four ways (× button, "Got it", backdrop click, Escape key).
 */
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import BlackjackRulesModal from "../src/components/BlackjackRulesModal";

describe("BlackjackRulesModal", () => {
  it("renders as a dialog with the title and key rules", () => {
    render(<BlackjackRulesModal onClose={() => {}} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/How to Play Blackjack/i)).toBeInTheDocument();
    expect(screen.getByText(/pays 3:2/i)).toBeInTheDocument();
    expect(screen.getByText(/hits on a soft 17/i)).toBeInTheDocument();
  });

  it("closes via the × button", () => {
    const onClose = vi.fn();
    render(<BlackjackRulesModal onClose={onClose} />);
    fireEvent.click(screen.getByLabelText(/close/i));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes via the "Got it" button', () => {
    const onClose = vi.fn();
    render(<BlackjackRulesModal onClose={onClose} />);
    fireEvent.click(screen.getByText(/Got it/i));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes when the backdrop is clicked", () => {
    const onClose = vi.fn();
    render(<BlackjackRulesModal onClose={onClose} />);
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<BlackjackRulesModal onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
