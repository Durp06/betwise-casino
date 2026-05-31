/**
 * HoldemSeat.test.tsx — renders a multiplayer Hold'em chair.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import HoldemSeat from "../src/components/HoldemSeat";
import type { HoldemSeat as HoldemSeatType, HoldemHandSeatState } from "../src/types";

function makeOccupant(overrides: Partial<HoldemSeatType> = {}): HoldemSeatType {
  return {
    id: "seat-1",
    user_id: "u1",
    seat_number: 0,
    stack: 10_000,
    status: "active",
    username: "alice",
    ...overrides,
  };
}

function makeHandSeat(overrides: Partial<HoldemHandSeatState> = {}): HoldemHandSeatState {
  return {
    seat_number: 0,
    table_seat_number: 0,
    user_id: "u1",
    username: "alice",
    hole_cards: [],
    starting_stack: 10_000,
    final_stack: 10_000,
    current_bet: 0,
    is_folded: false,
    is_all_in: false,
    ...overrides,
  };
}

describe("HoldemSeat", () => {
  it("renders the player's username", () => {
    render(
      <HoldemSeat chairNumber={0} occupant={makeOccupant({ username: "bob" })} handSeat={null}
        isCurrentToAct={false} isButton={false} isYou={false} />,
    );
    expect(screen.getByTestId("holdem-seat-name-0")).toHaveTextContent("bob");
  });

  it("renders an empty-seat placeholder when no one is there", () => {
    render(
      <HoldemSeat chairNumber={3} occupant={null} handSeat={null}
        isCurrentToAct={false} isButton={false} isYou={false} />,
    );
    expect(screen.getByText(/empty seat/i)).toBeInTheDocument();
  });

  it("shows the dealer button indicator when isButton", () => {
    render(
      <HoldemSeat chairNumber={0} occupant={makeOccupant()} handSeat={makeHandSeat()}
        isCurrentToAct={false} isButton={true} isYou={false} />,
    );
    expect(screen.getByTestId("dealer-button-indicator")).toBeInTheDocument();
  });

  it("shows the 'you' marker for the local player", () => {
    render(
      <HoldemSeat chairNumber={0} occupant={makeOccupant()} handSeat={makeHandSeat()}
        isCurrentToAct={false} isButton={false} isYou={true} />,
    );
    expect(screen.getByTestId("you-marker")).toBeInTheDocument();
  });

  it("masks opponent hole cards as card backs", () => {
    render(
      <HoldemSeat chairNumber={1} occupant={makeOccupant()} handSeat={makeHandSeat({ hole_cards: [null, null] })}
        isCurrentToAct={false} isButton={false} isYou={false} />,
    );
    expect(screen.getAllByTestId("hole-card-back").length).toBe(2);
  });

  it("renders the current bet when > 0", () => {
    render(
      <HoldemSeat chairNumber={2} occupant={makeOccupant()} handSeat={makeHandSeat({ current_bet: 300 })}
        isCurrentToAct={false} isButton={false} isYou={false} />,
    );
    expect(screen.getByTestId("holdem-seat-bet-2")).toHaveTextContent("300");
  });

  it("labels folded seats", () => {
    render(
      <HoldemSeat chairNumber={0} occupant={makeOccupant()} handSeat={makeHandSeat({ is_folded: true })}
        isCurrentToAct={false} isButton={false} isYou={false} />,
    );
    expect(screen.getByText(/folded/i)).toBeInTheDocument();
  });

  it("labels all-in seats", () => {
    render(
      <HoldemSeat chairNumber={0} occupant={makeOccupant()} handSeat={makeHandSeat({ is_all_in: true })}
        isCurrentToAct={false} isButton={false} isYou={false} />,
    );
    expect(screen.getByText(/all-in/i)).toBeInTheDocument();
  });
});
