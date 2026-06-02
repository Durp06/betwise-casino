/**
 * Board.test.tsx — board renders 0/3/4/5 cards with placeholder slots.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Board from "../src/components/Board";
import type { PokerCard } from "../src/types";

function card(suit: "hearts" | "diamonds" | "clubs" | "spades", value: string): PokerCard {
  return { suit, value: value as PokerCard["value"] };
}

describe("Board", () => {
  it("renders 5 empty slots when no cards", () => {
    render(<Board cards={[]} />);
    expect(screen.getAllByTestId("board-empty-slot").length).toBe(5);
  });

  it("renders 3 cards + 2 empty slots on the flop", () => {
    const cards = [card("hearts", "A"), card("spades", "K"), card("diamonds", "5")];
    render(<Board cards={cards} />);
    expect(screen.getAllByTestId("board-empty-slot").length).toBe(2);
  });

  it("renders all 5 cards on the river", () => {
    const cards = [
      card("hearts", "A"),
      card("spades", "K"),
      card("diamonds", "5"),
      card("clubs", "J"),
      card("hearts", "2"),
    ];
    render(<Board cards={cards} />);
    expect(screen.queryByTestId("board-empty-slot")).toBeNull();
  });
});
