/**
 * PokerSeat.test.tsx — renders the seat with archetype + stack + state.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PokerSeat from "../src/components/PokerSeat";
import type { PokerSeat as PokerSeatType, PokerHandSeatState } from "../src/types";

function makeSeat(overrides: Partial<PokerSeatType> = {}): PokerSeatType {
  return {
    seat_number: 0,
    user_id: null,
    archetype_name: "TAG",
    starting_stack: 1500,
    current_stack: 1500,
    is_bust: false,
    is_bot: true,
    ...overrides,
  };
}

function makeHandSeat(overrides: Partial<PokerHandSeatState> = {}): PokerHandSeatState {
  return {
    seat_number: 0,
    hole_cards: [],
    starting_stack: 1500,
    final_stack: 1500,
    current_bet: 0,
    is_folded: false,
    is_all_in: false,
    ...overrides,
  };
}

describe("PokerSeat", () => {
  it("renders archetype badge for a bot", () => {
    render(
      <PokerSeat
        seat={makeSeat({ archetype_name: "Maniac" })}
        handSeat={null}
        isCurrentToAct={false}
        isButton={false}
        isYou={false}
      />,
    );
    expect(screen.getByTestId("archetype-badge-Maniac")).toBeInTheDocument();
  });

  it("renders 'You' badge for the human seat", () => {
    render(
      <PokerSeat
        seat={makeSeat({ is_bot: false, archetype_name: null })}
        handSeat={null}
        isCurrentToAct={false}
        isButton={false}
        isYou={true}
      />,
    );
    expect(screen.getByTestId("archetype-badge-human")).toBeInTheDocument();
    expect(screen.getByTestId("you-marker")).toBeInTheDocument();
  });

  it("shows dealer button indicator when isButton is true", () => {
    render(
      <PokerSeat
        seat={makeSeat()}
        handSeat={null}
        isCurrentToAct={false}
        isButton={true}
        isYou={false}
      />,
    );
    expect(screen.getByTestId("dealer-button-indicator")).toBeInTheDocument();
  });

  it("shows masked hole-card backs when opponent cards are null", () => {
    render(
      <PokerSeat
        seat={makeSeat()}
        handSeat={makeHandSeat({ hole_cards: [null, null] })}
        isCurrentToAct={false}
        isButton={false}
        isYou={false}
      />,
    );
    expect(screen.getAllByTestId("hole-card-back").length).toBe(2);
  });

  it("renders current bet when > 0", () => {
    render(
      <PokerSeat
        seat={makeSeat()}
        handSeat={makeHandSeat({ current_bet: 250 })}
        isCurrentToAct={false}
        isButton={false}
        isYou={false}
      />,
    );
    expect(screen.getByTestId("seat-bet-0")).toHaveTextContent("250");
  });

  it("labels folded seats", () => {
    render(
      <PokerSeat
        seat={makeSeat()}
        handSeat={makeHandSeat({ is_folded: true })}
        isCurrentToAct={false}
        isButton={false}
        isYou={false}
      />,
    );
    expect(screen.getByText(/folded/i)).toBeInTheDocument();
  });

  it("labels all-in seats", () => {
    render(
      <PokerSeat
        seat={makeSeat()}
        handSeat={makeHandSeat({ is_all_in: true })}
        isCurrentToAct={false}
        isButton={false}
        isYou={false}
      />,
    );
    expect(screen.getByText(/all-in/i)).toBeInTheDocument();
  });
});
