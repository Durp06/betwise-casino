/**
 * PokerActionBar.test.tsx — fold/check/call/raise/all-in button legality.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import PokerActionBar from "../src/components/PokerActionBar";
import type { PokerHandSeatState, PokerHandState } from "../src/types";

vi.mock("../src/api/client", async () => {
  return {
    actPoker: vi.fn(async () => ({ data: { ok: true }, error: null })),
  };
});

const server = setupServer(
  http.post("/api/poker/tournaments/:tid/act", () => HttpResponse.json({ ok: true })),
);
beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterAll(() => server.close());
afterEach(() => server.resetHandlers());

function makeHand(overrides: Partial<PokerHandState> = {}): PokerHandState {
  return {
    id: "hand-1",
    hand_number: 1,
    button_seat: 0,
    small_blind: 5,
    big_blind: 10,
    ante: 0,
    board: [],
    pot_total: 30,
    side_pots: [],
    street: "preflop",
    current_bet_to_match: 10,
    current_to_act_seat: 0,
    last_aggressor_seat: null,
    min_raise_increment: 10,
    status: "active",
    seats: [],
    actions: [],
    ...overrides,
  };
}

function makeYourSeat(overrides: Partial<PokerHandSeatState> = {}): PokerHandSeatState {
  return {
    seat_number: 0,
    hole_cards: [],
    starting_stack: 1500,
    final_stack: 1490,
    current_bet: 0,
    is_folded: false,
    is_all_in: false,
    ...overrides,
  };
}

describe("PokerActionBar", () => {
  it("shows Check when there's no bet to call", () => {
    render(
      <PokerActionBar
        tournamentId="t-1"
        hand={makeHand({ current_bet_to_match: 0 })}
        yourSeat={makeYourSeat({ current_bet: 0 })}
      />,
    );
    expect(screen.getByTestId("poker-action-check")).toBeInTheDocument();
    expect(screen.queryByTestId("poker-action-call")).toBeNull();
  });

  it("shows Call when facing a bet", () => {
    render(
      <PokerActionBar
        tournamentId="t-1"
        hand={makeHand({ current_bet_to_match: 30 })}
        yourSeat={makeYourSeat({ current_bet: 10 })}
      />,
    );
    expect(screen.getByTestId("poker-action-call")).toHaveTextContent("20");
  });

  it("always shows Fold and All-in", () => {
    render(
      <PokerActionBar
        tournamentId="t-1"
        hand={makeHand()}
        yourSeat={makeYourSeat()}
      />,
    );
    expect(screen.getByTestId("poker-action-fold")).toBeInTheDocument();
    expect(screen.getByTestId("poker-action-all_in")).toBeInTheDocument();
  });

  it("opens the slider when Raise is clicked", async () => {
    const user = userEvent.setup();
    render(
      <PokerActionBar
        tournamentId="t-1"
        hand={makeHand()}
        yourSeat={makeYourSeat()}
      />,
    );
    await user.click(screen.getByTestId("poker-action-raise"));
    expect(screen.getByTestId("bet-sizing-slider")).toBeInTheDocument();
  });
});
