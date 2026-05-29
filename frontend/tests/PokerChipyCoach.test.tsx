/**
 * PokerChipyCoach.test.tsx — covers the Reads/Odds toggle persistence and
 * the confidence-tier badge.
 */
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, expect } from "vitest";
import PokerChipyCoach from "../src/components/PokerChipyCoach";
import { useGameStore } from "../src/store/gameStore";

beforeEach(() => {
  try {
    window.localStorage.removeItem("betwise.pokerCoachMode");
  } catch {
    // ignore
  }
  act(() => {
    useGameStore.setState({
      pokerCoachMode: "odds",
      pokerCoachText: "",
      pokerCoachStreaming: false,
      pokerCoachConfidenceTier: null,
      pokerCoachRecommendedAction: null,
    });
  });
});

describe("PokerChipyCoach", () => {
  it("renders both mode toggle pills", () => {
    render(<PokerChipyCoach handId={null} />);
    expect(screen.getByTestId("poker-coach-mode-reads")).toBeInTheDocument();
    expect(screen.getByTestId("poker-coach-mode-odds")).toBeInTheDocument();
  });

  it("clicking Reads persists the choice to localStorage", async () => {
    const user = userEvent.setup();
    render(<PokerChipyCoach handId={null} />);
    expect(useGameStore.getState().pokerCoachMode).toBe("odds");
    await user.click(screen.getByTestId("poker-coach-mode-reads"));
    expect(useGameStore.getState().pokerCoachMode).toBe("reads");
    expect(window.localStorage.getItem("betwise.pokerCoachMode")).toBe("reads");
  });

  it("shows the DETERMINISTIC badge when the store has that confidence tier", () => {
    act(() => {
      useGameStore.setState({
        pokerCoachConfidenceTier: "DETERMINISTIC",
        pokerCoachText: "Push ace-king here.",
        pokerCoachRecommendedAction: "all_in",
      });
    });
    render(<PokerChipyCoach handId={null} />);
    expect(screen.getByTestId("confidence-tier-DETERMINISTIC")).toBeInTheDocument();
    expect(screen.getByTestId("poker-coach-recommended")).toHaveTextContent("all_in");
  });

  it("shows the HEURISTIC badge when the store has that confidence tier", () => {
    act(() => {
      useGameStore.setState({
        pokerCoachConfidenceTier: "HEURISTIC",
        pokerCoachText: "Use principle-based reasoning here.",
      });
    });
    render(<PokerChipyCoach handId={null} />);
    expect(screen.getByTestId("confidence-tier-HEURISTIC")).toBeInTheDocument();
  });

  it("disables Ask Chipy button when handId is null", () => {
    render(<PokerChipyCoach handId={null} />);
    expect(screen.getByTestId("poker-coach-fetch")).toBeDisabled();
  });
});
