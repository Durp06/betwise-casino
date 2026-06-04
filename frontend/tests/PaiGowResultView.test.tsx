/**
 * PaiGowResultView.test.tsx — verifies the post-resolve comparison panel
 * renders dealer + player splits side-by-side, the correct per-side outcome
 * chip (WON / LOST / COPY → DEALER), the verdict heading, payouts, and the
 * both-sides-must-win explainer line.
 *
 * Covers AC for the result-screen UX improvement (front/back split with
 * comparison + per-side winner labels).
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PaiGowResultView from "../src/components/PaiGowResultView";
import type {
  PaiGowCard,
  PaiGowHandResult,
  PaiGowPlayerHand,
  PaiGowRound,
  PaiGowSideCompare,
} from "../src/types";

const dealerFront: PaiGowCard[] = [
  { suit: "spades", value: "2" },
  { suit: "hearts", value: "3" },
];
const dealerBack: PaiGowCard[] = [
  { suit: "spades", value: "4" },
  { suit: "clubs", value: "5" },
  { suit: "diamonds", value: "7" },
  { suit: "hearts", value: "10" },
  { suit: "spades", value: "Q" },
];
const playerFront: PaiGowCard[] = [
  { suit: "hearts", value: "A" },
  { suit: "diamonds", value: "A" },
];
const playerBack: PaiGowCard[] = [
  { suit: "spades", value: "K" },
  { suit: "clubs", value: "K" },
  { suit: "diamonds", value: "K" },
  { suit: "hearts", value: "K" },
  { suit: "spades", value: "9" },
];

function makeRound(): PaiGowRound {
  return {
    id: "r-1",
    table_id: "t-1",
    round_number: 1,
    dealer_dealt_cards: [...dealerFront, ...dealerBack],
    dealer_front: dealerFront,
    dealer_back: dealerBack,
    status: "finished",
    playing_started_at: "2026-06-04T00:00:00Z",
    created_at: "2026-06-04T00:00:00Z",
    resolved_at: "2026-06-04T00:00:01Z",
  };
}

interface HandOpts {
  front_compare: PaiGowSideCompare;
  back_compare: PaiGowSideCompare;
  hand_result: PaiGowHandResult;
  ante_payout_cents: number;
  fortune_payout_cents?: number | null;
}

function makeHand(opts: HandOpts): PaiGowPlayerHand {
  return {
    id: "h-1",
    round_id: "r-1",
    user_id: "u-1",
    dealt_cards: [...playerFront, ...playerBack],
    front_cards: playerFront,
    back_cards: playerBack,
    bet_cents: 1_000,
    fortune_bet_cents: 0,
    front_compare: opts.front_compare,
    back_compare: opts.back_compare,
    hand_result: opts.hand_result,
    ante_payout_cents: opts.ante_payout_cents,
    fortune_payout_cents: opts.fortune_payout_cents ?? null,
    action_status: "resolved",
    created_at: "2026-06-04T00:00:00Z",
    resolved_at: "2026-06-04T00:00:01Z",
  };
}

describe("PaiGowResultView", () => {
  it("both sides won (player+player) → 'You win!' + two WON chips + win explainer", () => {
    const round = makeRound();
    const myHand = makeHand({
      front_compare: "player",
      back_compare: "player",
      hand_result: "win",
      ante_payout_cents: 2_000,
    });
    render(<PaiGowResultView round={round} myHand={myHand} />);

    expect(screen.getByText("You win!")).toBeInTheDocument();
    expect(screen.getByText("Both sides won — you collect.")).toBeInTheDocument();

    const frontChip = screen.getByTestId("player-front-chip");
    const backChip = screen.getByTestId("player-back-chip");
    expect(frontChip).toHaveTextContent("Won");
    expect(backChip).toHaveTextContent("Won");
    // Both green (action-stand) — assert the class is present.
    expect(frontChip.className).toContain("bg-action-stand");
    expect(backChip.className).toContain("bg-action-stand");
  });

  it("both sides lost (banker+banker) → 'Dealer wins' + two LOST chips + lose explainer", () => {
    const round = makeRound();
    const myHand = makeHand({
      front_compare: "banker",
      back_compare: "banker",
      hand_result: "lose",
      ante_payout_cents: -1_000,
    });
    render(<PaiGowResultView round={round} myHand={myHand} />);

    expect(screen.getByText("Dealer wins")).toBeInTheDocument();
    expect(screen.getByText("Lost both — dealer wins.")).toBeInTheDocument();

    const frontChip = screen.getByTestId("player-front-chip");
    const backChip = screen.getByTestId("player-back-chip");
    expect(frontChip).toHaveTextContent("Lost");
    expect(backChip).toHaveTextContent("Lost");
    expect(frontChip.className).toContain("bg-action-hit");
    expect(backChip.className).toContain("bg-action-hit");
  });

  it("one-and-one (player+banker) → 'Push' + one WON + one LOST chip + push explainer", () => {
    const round = makeRound();
    const myHand = makeHand({
      front_compare: "player",
      back_compare: "banker",
      hand_result: "push",
      ante_payout_cents: 0,
    });
    render(<PaiGowResultView round={round} myHand={myHand} />);

    expect(screen.getByText("Push")).toBeInTheDocument();
    expect(screen.getByText("Won one, lost one — push.")).toBeInTheDocument();

    expect(screen.getByTestId("player-front-chip")).toHaveTextContent("Won");
    expect(screen.getByTestId("player-back-chip")).toHaveTextContent("Lost");
  });

  it("copy on the front → amber COPY → DEALER chip on the front side", () => {
    const round = makeRound();
    const myHand = makeHand({
      front_compare: "copy",
      back_compare: "banker",
      hand_result: "lose",
      ante_payout_cents: -1_000,
    });
    render(<PaiGowResultView round={round} myHand={myHand} />);

    const frontChip = screen.getByTestId("player-front-chip");
    expect(frontChip).toHaveTextContent("Copy → dealer");
    expect(frontChip.className).toContain("bg-gold-mid");
    // Back side still LOST (banker).
    expect(screen.getByTestId("player-back-chip")).toHaveTextContent("Lost");
  });

  it("renders dealer + player splits and Fortune payout when present", () => {
    const round = makeRound();
    const myHand = makeHand({
      front_compare: "player",
      back_compare: "player",
      hand_result: "win",
      ante_payout_cents: 2_000,
      fortune_payout_cents: 500,
    });
    render(<PaiGowResultView round={round} myHand={myHand} />);

    // Dealer front has 2 cards, dealer back has 5; same for player.
    const dealerFrontRow = screen.getByTestId("dealer-front");
    const dealerBackRow = screen.getByTestId("dealer-back");
    const playerFrontRow = screen.getByTestId("player-front");
    const playerBackRow = screen.getByTestId("player-back");

    // Each card renders as a div with an aria-label or the inner PlayingCard.
    // We count the immediate children of each row.
    expect(dealerFrontRow.children.length).toBe(2);
    expect(dealerBackRow.children.length).toBe(5);
    expect(playerFrontRow.children.length).toBe(2);
    expect(playerBackRow.children.length).toBe(5);

    // Fortune payout shown alongside the Ante.
    const resultView = screen.getByTestId("pai-gow-result-view");
    expect(within(resultView).getByText(/Ante/)).toBeInTheDocument();
    expect(within(resultView).getByText(/Fortune/)).toBeInTheDocument();
  });
});
