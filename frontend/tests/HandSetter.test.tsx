/**
 * HandSetter.test.tsx — spec AC-T8.
 *
 * Verifies tap-to-assign, exactly-2 enforcement, submit-disabled-until-2,
 * and front draft clearing. Submit / SSE flows are mocked at the client.ts
 * boundary so this stays focused on the component's local logic.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HandSetter from "../src/components/HandSetter";
import { usePaiGowStore } from "../src/store/paiGowStore";
import type { PaiGowCard, PaiGowPlayerHand } from "../src/types";

vi.mock("../src/api/client", () => ({
  setPaiGowHand: vi.fn(async () => ({ data: null, error: "mocked" })),
}));

const sevenCards: PaiGowCard[] = [
  { suit: "hearts", value: "A" },
  { suit: "spades", value: "K" },
  { suit: "diamonds", value: "Q" },
  { suit: "clubs", value: "J" },
  { suit: "hearts", value: "9" },
  { suit: "spades", value: "5" },
  { suit: "clubs", value: "3" },
];

function makeHand(): PaiGowPlayerHand {
  return {
    id: "h-1",
    round_id: "r-1",
    user_id: "u-1",
    dealt_cards: sevenCards,
    front_cards: null,
    back_cards: null,
    bet_cents: 1_000,
    fortune_bet_cents: 0,
    front_compare: null,
    back_compare: null,
    hand_result: null,
    ante_payout_cents: null,
    fortune_payout_cents: null,
    action_status: "dealt",
    created_at: "2026-06-02T00:00:00Z",
    resolved_at: null,
  };
}

beforeEach(() => {
  usePaiGowStore.setState({
    tableState: null,
    myHand: null,
    frontDraft: [],
    chipyText: "",
    chipyStreaming: false,
    chipyPhase: "idle",
    chipyHandId: null,
    preOptimal: null,
    postEvaluation: null,
    lastFinishedHandId: null,
  });
});

afterEach(() => {
  vi.clearAllMocks();
});


describe("HandSetter", () => {
  it("renders all 7 dealt cards as tappable buttons", () => {
    render(<HandSetter hand={makeHand()} onSubmitted={() => {}} />);
    const buttons = screen.getAllByRole("button", { pressed: false });
    // 7 card buttons + the Clear / Set Hand buttons; just check ≥ 7 cards.
    expect(buttons.length).toBeGreaterThanOrEqual(7);
  });

  it("submit button is disabled until exactly 2 cards are in the front", async () => {
    const user = userEvent.setup();
    render(<HandSetter hand={makeHand()} onSubmitted={() => {}} />);

    const submit = screen.getByRole("button", { name: /set hand/i });
    expect(submit).toBeDisabled();

    // Tap 1 card → still disabled.
    const cardButtons = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-pressed") !== null);
    await user.click(cardButtons[0]);
    expect(submit).toBeDisabled();

    // Tap a second card → enabled.
    await user.click(cardButtons[1]);
    expect(submit).not.toBeDisabled();
  });

  it("tapping a 3rd card is a no-op (front capped at 2)", async () => {
    const user = userEvent.setup();
    render(<HandSetter hand={makeHand()} onSubmitted={() => {}} />);
    const cardButtons = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-pressed") !== null);
    await user.click(cardButtons[0]);
    await user.click(cardButtons[1]);
    await user.click(cardButtons[2]);
    // frontDraft should still be 2 in the store.
    expect(usePaiGowStore.getState().frontDraft.length).toBe(2);
  });

  it("tapping a selected card toggles it back out", async () => {
    const user = userEvent.setup();
    render(<HandSetter hand={makeHand()} onSubmitted={() => {}} />);
    const cardButtons = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-pressed") !== null);
    await user.click(cardButtons[0]);
    expect(usePaiGowStore.getState().frontDraft.length).toBe(1);
    await user.click(cardButtons[0]);
    expect(usePaiGowStore.getState().frontDraft.length).toBe(0);
  });

  it("Clear button empties the front draft", async () => {
    const user = userEvent.setup();
    render(<HandSetter hand={makeHand()} onSubmitted={() => {}} />);
    const cardButtons = screen
      .getAllByRole("button")
      .filter((b) => b.getAttribute("aria-pressed") !== null);
    await user.click(cardButtons[0]);
    await user.click(cardButtons[1]);
    const clear = screen.getByRole("button", { name: /clear/i });
    await user.click(clear);
    expect(usePaiGowStore.getState().frontDraft.length).toBe(0);
  });
});
