"""
engine.py — pure deck/hand helpers for BetWise Casino blackjack.

Design constraints (specs/betwise-casino.md §T5):
- All functions are pure (no DB, no network).
- create_deck(seed) is seedable for deterministic tests.
- deal_card does NOT mutate its input list.
- hand_value uses soft-ace logic: count aces as 11, demote one at a time.
- can_split: face cards (J/Q/K) collapse to value 10 for pairing purposes.
"""

from __future__ import annotations

import random
from typing import TypedDict


# ─── Card type ────────────────────────────────────────────────────────────────

class Card(TypedDict):
    suit: str
    value: str


SUITS = ["hearts", "diamonds", "clubs", "spades"]
VALUES = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


# ─── Deck helpers ─────────────────────────────────────────────────────────────

def create_deck(seed: int | None = None) -> list[Card]:
    """Return a freshly shuffled 52-card deck.

    With a seed, the shuffle is deterministic — same seed → same order.
    Without a seed, shuffle is random.
    """
    deck: list[Card] = [
        {"suit": suit, "value": value}
        for suit in SUITS
        for value in VALUES
    ]
    rng = random.Random(seed)
    rng.shuffle(deck)
    return deck


def deal_card(deck: list[Card]) -> tuple[Card, list[Card]]:
    """Pop the top card from a deck and return (card, remaining_deck).

    Does NOT mutate the input list — returns a new list for the remainder.
    """
    if not deck:
        raise ValueError("Cannot deal from an empty deck")
    card = deck[0]
    remaining = deck[1:]
    return card, remaining


# ─── Hand scoring ─────────────────────────────────────────────────────────────

def card_rank(card: Card) -> int:
    """Return numeric rank: 2-9 as-is, 10/J/Q/K → 10, A → 11."""
    v = card["value"]
    if v in ("J", "Q", "K"):
        return 10
    if v == "A":
        return 11
    return int(v)


def hand_value(cards: list[Card]) -> int:
    """Compute the best hand value with soft-ace logic.

    Aces start as 11; each is demoted to 1 one at a time while the total
    exceeds 21.
    """
    total = 0
    aces = 0
    for card in cards:
        r = card_rank(card)
        if card["value"] == "A":
            aces += 1
        total += r
    # Demote aces one at a time while bust
    while total > 21 and aces > 0:
        total -= 10  # demote one ace: 11 → 1 = subtract 10
        aces -= 1
    return total


def is_soft(cards: list[Card]) -> bool:
    """Return True when at least one ace is still counted as 11."""
    total = 0
    aces = 0
    for card in cards:
        r = card_rank(card)
        if card["value"] == "A":
            aces += 1
        total += r
    # Count demotions needed
    demotions = 0
    while total > 21 and demotions < aces:
        total -= 10
        demotions += 1
    # Soft if we have aces left that haven't been demoted (counting as 11)
    return (aces - demotions) > 0


def is_blackjack(cards: list[Card]) -> bool:
    """Return True iff exactly 2 cards total 21."""
    return len(cards) == 2 and hand_value(cards) == 21


def is_bust(cards: list[Card]) -> bool:
    """Return True iff the hand value exceeds 21."""
    return hand_value(cards) > 21


# ─── Legality helpers ─────────────────────────────────────────────────────────

def _split_rank(card: Card) -> int:
    """Rank for split comparison: J/Q/K/10 all collapse to 10, A stays as A (special)."""
    v = card["value"]
    if v in ("J", "Q", "K"):
        return 10
    if v == "A":
        return 11  # aces pair with aces only
    return int(v)


def can_split(cards: list[Card]) -> bool:
    """Return True iff exactly 2 cards with the same split-rank.

    Face cards (J/Q/K) collapse to rank 10, so K-Q is a splittable pair.
    """
    if len(cards) != 2:
        return False
    return _split_rank(cards[0]) == _split_rank(cards[1])


def can_double(cards: list[Card]) -> bool:
    """Return True iff exactly 2 cards (doubling is legal only on first two cards)."""
    return len(cards) == 2
