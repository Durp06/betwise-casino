/**
 * HoldemActionBar.test.tsx — fold/check/call/raise/all-in legality + slider.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import HoldemActionBar from "../src/components/HoldemActionBar";
import type { HoldemHandState, HoldemHandSeatState } from "../src/types";

// vi.hoisted so the mock fn exists before vi.mock's (hoisted) factory runs.
const { actHoldemMock } = vi.hoisted(() => ({ actHoldemMock: vi.fn() }));
vi.mock("../src/api/client", () => ({ actHoldem: actHoldemMock }));

beforeEach(() => {
  actHoldemMock.mockReset();
  actHoldemMock.mockResolvedValue({ data: {}, error: null });
});

function makeHand(overrides: Partial<HoldemHandState> = {}): HoldemHandState {
  return {
    id: "h1",
    hand_number: 1,
    button_seat: 0,
    small_blind: 50,
    big_blind: 100,
    board: [],
    pot_total: 150,
    side_pots: [],
    street: "preflop",
    current_bet_to_match: 100,
    current_to_act_seat: 0,
    last_aggressor_seat: null,
    min_raise_increment: 100,
    status: "active",
    result: null,
    seats: [],
    actions: [],
    ...overrides,
  };
}

function makeSeat(overrides: Partial<HoldemHandSeatState> = {}): HoldemHandSeatState {
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

describe("HoldemActionBar", () => {
  it("always shows fold and all-in", () => {
    render(<HoldemActionBar tableId="t1" hand={makeHand()} yourSeat={makeSeat()} />);
    expect(screen.getByTestId("holdem-action-fold")).toBeInTheDocument();
    expect(screen.getByTestId("holdem-action-all_in")).toBeInTheDocument();
  });

  it("shows Call when facing a bet", () => {
    // current_bet_to_match 100, your current_bet 0 → toCall 100 → Call.
    render(<HoldemActionBar tableId="t1" hand={makeHand()} yourSeat={makeSeat({ current_bet: 0 })} />);
    expect(screen.getByTestId("holdem-action-call")).toBeInTheDocument();
    expect(screen.queryByTestId("holdem-action-check")).not.toBeInTheDocument();
  });

  it("shows Check when nothing to call", () => {
    render(
      <HoldemActionBar
        tableId="t1"
        hand={makeHand({ current_bet_to_match: 0 })}
        yourSeat={makeSeat({ current_bet: 0 })}
      />,
    );
    expect(screen.getByTestId("holdem-action-check")).toBeInTheDocument();
    expect(screen.queryByTestId("holdem-action-call")).not.toBeInTheDocument();
  });

  it("opens the bet-sizing slider when Raise is clicked", () => {
    render(<HoldemActionBar tableId="t1" hand={makeHand()} yourSeat={makeSeat()} />);
    expect(screen.queryByTestId("bet-sizing-slider")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("holdem-action-raise"));
    expect(screen.getByTestId("bet-sizing-slider")).toBeInTheDocument();
    expect(screen.getByTestId("holdem-action-raise-confirm")).toBeInTheDocument();
  });

  it("disables Raise when the stack can't cover a min-raise", () => {
    // stack 50 < min_raise_increment 100 → Raise disabled.
    render(<HoldemActionBar tableId="t1" hand={makeHand()} yourSeat={makeSeat({ final_stack: 50 })} />);
    expect(screen.getByTestId("holdem-action-raise")).toBeDisabled();
  });

  it("disables All-in when the stack is zero", () => {
    render(<HoldemActionBar tableId="t1" hand={makeHand()} yourSeat={makeSeat({ final_stack: 0 })} />);
    expect(screen.getByTestId("holdem-action-all_in")).toBeDisabled();
  });

  it("dispatches the correct action+amount when Fold is clicked", async () => {
    render(<HoldemActionBar tableId="t1" hand={makeHand()} yourSeat={makeSeat()} />);
    fireEvent.click(screen.getByTestId("holdem-action-fold"));
    await waitFor(() => expect(actHoldemMock).toHaveBeenCalledWith("t1", "fold", 0));
  });

  it("dispatches a call when facing a bet", async () => {
    render(<HoldemActionBar tableId="t1" hand={makeHand()} yourSeat={makeSeat({ current_bet: 0 })} />);
    fireEvent.click(screen.getByTestId("holdem-action-call"));
    await waitFor(() => expect(actHoldemMock).toHaveBeenCalledWith("t1", "call", 0));
  });
});
